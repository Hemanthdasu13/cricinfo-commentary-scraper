from __future__ import annotations

from pathlib import Path

from cricketiq.contextual_value import (
    ContextBall,
    leave_batter_out_expectations,
    player_delivery_patterns,
    player_contextual_value,
    refresh_contextual_value_memory,
)
from cricketiq.database import connect
from cricketiq.model_validation import validate_by_season


def _ball(batter: str, runs: int) -> ContextBall:
    return ContextBall(
        batter_name=batter,
        batter_id=batter,
        match_format="T20",
        competition="Indian Premier League",
        phase="powerplay",
        bowling_type="Left-arm orthodox",
        wickets_before=0,
        score_band=0,
        innings_group="first",
        batter_runs=runs,
    )


def test_leave_batter_out_does_not_use_the_scored_batters_own_runs() -> None:
    # The comparison pool is 120 one-run balls by other batters.  A's 4s must
    # not inflate their own baseline; their expected score stays one per ball.
    events = [_ball("A", 4) for _ in range(2)] + [_ball("B", 1) for _ in range(60)] + [_ball("C", 1) for _ in range(60)]
    scored = leave_batter_out_expectations(events, minimum_comparison_events=100)
    a_scores = [event for event in scored if event.ball.batter_name == "A"]
    assert len(a_scores) == 2
    assert {event.expected_runs for event in a_scores} == {1.0}
    assert {event.comparator_events for event in a_scores} == {120}


def test_single_batter_is_not_given_a_leaky_baseline() -> None:
    assert leave_batter_out_expectations([_ball("A", 6) for _ in range(120)]) == []


def test_refresh_persists_context_adjusted_overall_and_type_matchups() -> None:
    connection = connect(Path(":memory:"))
    try:
        connection.execute(
            "INSERT INTO matches VALUES ('m1', '2025-01-01', 'Indian Premier League', '2025', 'T20', "
            "'male', 'club', '[\"A\", \"B\"]', '', '', 'fixture')"
        )
        connection.executemany(
            "INSERT INTO match_players VALUES (?, ?, ?, ?)",
            [("m1", "A", "a", "1"), ("m1", "B", "b", "2"), ("m1", "C", "c", "3"), ("m1", "Spinner", "s", "4")],
        )
        connection.execute(
            "INSERT INTO players VALUES ('s', 'Spinner', '4', 'Spinner', 1, 'B', '', 'left', 'spin', "
            "'left-arm orthodox', '', '', 'ok')"
        )
        deliveries = []
        # These deliberately use a simple synthetic innings.  The extractor
        # only relies on chronological source facts and pre-delivery state.
        for index, (batter, runs) in enumerate(
            [("A", 2)] * 60 + [("B", 1)] * 60 + [("C", 1)] * 60, start=1
        ):
            deliveries.append(("m1", 1, index, f"0.{index}", 1, batter, "Spinner", "Other", runs, 0, runs, "", "", "fixture"))
        connection.executemany("INSERT INTO deliveries VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", deliveries)
        connection.executemany(
            "INSERT INTO commentary_links VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [("commentary.csv", index, "m1", 1, index, "linked", 1, "fixture") for index in range(1, 61)],
        )
        connection.executemany(
            "INSERT INTO commentary_tags VALUES (?, ?, ?, ?, ?)",
            [("commentary.csv", index, "length", "full", "full") for index in range(1, 61)],
        )
        refresh_contextual_value_memory(connection)
        card = player_contextual_value(connection, "A")
        assert card["overall"]["non_wide_events"] == 60
        assert card["overall"]["runs_above_expected"] == 60.0
        assert card["matchups"][0]["bowling_type"] == "Left-arm orthodox"
        assert card["matchups"][0]["runs_above_expected_per_100"] == 100.0
        patterns = player_delivery_patterns(connection, "A")
        assert patterns[0]["tag_value"] == "full"
        assert patterns[0]["tagged_events"] == 60
        assert patterns[0]["tag_share_pct"] == 100.0
        assert patterns[0]["commentary_link_coverage_pct"] == 100.0
    finally:
        connection.close()


def test_temporal_validation_fits_only_earlier_seasons() -> None:
    connection = connect(Path(":memory:"))
    try:
        connection.executemany(
            "INSERT INTO matches VALUES (?, ?, 'Indian Premier League', ?, 'T20', 'male', 'club', "
            "'[\"A\", \"B\"]', '', '', 'fixture')",
            [("old", "2024-01-01", "2024"), ("new", "2025-01-01", "2025")],
        )
        connection.executemany(
            "INSERT INTO match_players VALUES (?, ?, ?, ?)",
            [(match, name, name.lower(), name) for match in ("old", "new") for name in ("A", "Spinner", "Pacer")],
        )
        connection.executemany(
            "INSERT INTO players VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [("spinner", "Spinner", "Spinner", "Spinner", 1, "B", "", "left", "spin", "left-arm orthodox", "", "", "ok"),
             ("pacer", "Pacer", "Pacer", "Pacer", 1, "B", "", "right", "pace", "fast", "", "", "ok")],
        )
        rows = []
        for match, count in (("old", 240), ("new", 20)):
            for index in range(1, count + 1):
                spin = index % 2 == 0
                runs = 0 if spin else 2
                rows.append((match, 1, index, f"0.{index}", 1, "A", "Spinner" if spin else "Pacer", "Other", runs, 0, runs, "", "", "fixture"))
        connection.executemany("INSERT INTO deliveries VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
        report = validate_by_season(connection, "2025")
        assert report.training_events == 240
        assert report.test_events == 20
        assert report.model_coverage == 1.0
        assert report.model_mean_squared_error < report.phase_mean_squared_error
    finally:
        connection.close()
