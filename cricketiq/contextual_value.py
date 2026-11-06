"""Context-adjusted batting value inspired by Deep Point's RAA approach.

The model asks a deliberately narrow question: given the phase, innings,
wickets already lost, score band and bowling *type*, how many batter runs
would an average other batter have scored?  A player's actual runs less that
expectation are Runs Above Expected (RAE).

This is a retrospective performance measure, not a forecast of a named
batter-v-bowler contest.  Cricsheet has no ball-tracking coordinates, so it
does not make claims about exact line, length, speed, shot, or field.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import dataclass
import json
from typing import Any, Iterable

import duckdb
import pandas as pd

from cricketiq.config import DEFAULT_DB_PATH
from cricketiq.database import connect


MIN_COMPARISON_EVENTS = 100
MIN_PLAYER_EVENTS = 50


@dataclass(frozen=True)
class ContextBall:
    """One legal-or-no-ball batter event with information known before it."""

    batter_name: str
    batter_id: str
    match_format: str
    competition: str
    phase: str
    bowling_type: str
    wickets_before: int
    score_band: int
    innings_group: str
    batter_runs: int
    match_id: str = ""
    innings_number: int = 0
    delivery_index: int = 0
    season: str = ""


@dataclass(frozen=True)
class ExpectedBall:
    """A source ball and its leave-batter-out expectation."""

    ball: ContextBall
    expected_runs: float
    comparator_events: int


def bowling_type_label(arm: str, kind: str, bowl_type: str) -> str:
    """Return the human-readable bowling-type label used across the product."""
    if not kind or not bowl_type:
        return "Unknown bowling type"
    if bowl_type.startswith("left-arm"):
        return bowl_type.replace("left-arm", "Left-arm", 1)
    if kind == "pace":
        return f"{arm.title()}-arm {bowl_type}"
    if bowl_type in {"off-break", "leg-break"}:
        return f"{arm.title()}-arm {bowl_type}"
    if bowl_type == "wrist spin":
        return f"{arm.title()}-arm wrist spin"
    return f"{arm.title()}-arm {bowl_type}"


def phase_for_ball(match_format: str, over_number: int) -> str:
    """Use transparent format-specific phase boundaries, with no hidden ML."""
    upper = match_format.upper()
    if upper in {"T20", "T10"}:
        return "powerplay" if over_number <= 6 else "middle" if over_number <= 15 else "death"
    if upper == "ODI":
        return "powerplay" if over_number <= 10 else "middle" if over_number <= 40 else "death"
    return "early" if over_number <= 20 else "middle" if over_number <= 60 else "late"


def _events(connection: duckdb.DuckDBPyConnection) -> list[ContextBall]:
    """Create chronologically correct, pre-delivery state records from source facts."""
    rows = connection.execute(
        """
        SELECT d.match_id, d.innings_number, d.delivery_index, d.over_number,
               d.batter, COALESCE(bat.cricinfo_id, ''), m.format, m.competition, m.season,
               COALESCE(profile.bowl_arm, ''), COALESCE(profile.bowl_kind, ''),
               COALESCE(profile.bowl_type, ''), d.batter_runs, d.total_runs,
               COALESCE(d.extras_json, ''), COALESCE(d.wickets_json, '')
        FROM deliveries d
        JOIN matches m ON m.match_id = d.match_id
        LEFT JOIN match_players bat ON bat.match_id = d.match_id AND bat.player_name = d.batter
        LEFT JOIN match_players bowl ON bowl.match_id = d.match_id AND bowl.player_name = d.bowler
        LEFT JOIN players profile ON profile.cricsheet_id = bowl.cricsheet_id
        ORDER BY d.match_id, d.innings_number, d.delivery_index
        """
    ).fetchall()

    events: list[ContextBall] = []
    state: dict[tuple[str, int], dict[str, int]] = defaultdict(lambda: {"runs": 0, "wickets": 0})
    for (match_id, innings_number, _index, over_number, batter, batter_id, match_format, competition, season,
         arm, kind, bowl_type, batter_runs, total_runs, extras_json, wickets_json) in rows:
        current = state[(match_id, innings_number)]
        is_wide = '"wides"' in extras_json
        if not is_wide:
            events.append(ContextBall(
                batter_name=batter,
                batter_id=batter_id,
                match_format=match_format,
                competition=competition,
                phase=phase_for_ball(match_format, over_number),
                bowling_type=bowling_type_label(arm, kind, bowl_type),
                wickets_before=min(current["wickets"], 5),
                score_band=current["runs"] // 10,
                innings_group="first" if innings_number == 1 else "chase",
                batter_runs=int(batter_runs),
                match_id=match_id,
                innings_number=int(innings_number),
                delivery_index=int(_index),
                season=str(season),
            ))
        current["runs"] += int(total_runs)
        # Each JSON wicket is counted for the score state.  This includes run
        # outs because the next batter really does face a changed situation.
        current["wickets"] += wickets_json.count('"player_out"')
    return events


def _context_keys(ball: ContextBall, *, include_bowling_type: bool) -> Iterable[tuple[Any, ...]]:
    """Yield a fixed back-off hierarchy from most to least specific context."""
    prefix: tuple[Any, ...] = (ball.match_format, ball.competition, ball.innings_group, ball.phase)
    suffix: tuple[Any, ...] = (ball.bowling_type,) if include_bowling_type else ()
    yield (*prefix, ball.wickets_before, ball.score_band, *suffix)
    yield (*prefix, ball.wickets_before, *suffix)
    yield (*prefix, *suffix)
    # A final phase baseline avoids silently dropping a player with an unusual
    # competition-specific state while still retaining the format and phase.
    yield (ball.match_format, ball.phase, *suffix)


def leave_batter_out_expectations(
    events: Iterable[ContextBall], *, include_bowling_type: bool = True,
    minimum_comparison_events: int = MIN_COMPARISON_EVENTS,
) -> list[ExpectedBall]:
    """Score events against a leave-batter-out, hierarchically backed-off pool.

    Aggregate counts are constructed once; for each focal event, its batter's
    complete contribution is subtracted from every candidate pool.  The result
    therefore cannot improve merely because that batter's own good innings
    raised the benchmark.
    """
    items = list(events)
    totals: dict[tuple[Any, ...], list[int]] = defaultdict(lambda: [0, 0])
    by_batter: dict[tuple[tuple[Any, ...], str], list[int]] = defaultdict(lambda: [0, 0])
    for ball in items:
        for key in _context_keys(ball, include_bowling_type=include_bowling_type):
            totals[key][0] += 1
            totals[key][1] += ball.batter_runs
            by_batter[(key, ball.batter_name)][0] += 1
            by_batter[(key, ball.batter_name)][1] += ball.batter_runs

    scored: list[ExpectedBall] = []
    for ball in items:
        fallback: tuple[int, int] | None = None
        for key in _context_keys(ball, include_bowling_type=include_bowling_type):
            count, runs = totals[key]
            own_count, own_runs = by_batter[(key, ball.batter_name)]
            other_count, other_runs = count - own_count, runs - own_runs
            if other_count:
                fallback = (other_count, other_runs)
            if other_count >= minimum_comparison_events:
                break
        if fallback is None:
            # A dataset with only one batter has no honest comparator.  Do not
            # manufacture a number by leaking their output into the baseline.
            continue
        comparator_count, comparator_runs = fallback
        scored.append(ExpectedBall(ball, comparator_runs / comparator_count, comparator_count))
    return scored


def _evidence_level(events: int, comparator_events: int) -> str:
    if events >= 150 and comparator_events >= MIN_COMPARISON_EVENTS:
        return "high"
    if events >= MIN_PLAYER_EVENTS:
        return "moderate"
    return "limited"


def refresh_contextual_value_memory(connection: duckdb.DuckDBPyConnection) -> None:
    """Refresh persistent RAE and type-level matchup read models after import."""
    connection.execute("DELETE FROM player_context_value_memory")
    connection.execute("DELETE FROM player_context_matchup_memory")
    connection.execute("DELETE FROM player_delivery_pattern_memory")
    expected = leave_batter_out_expectations(_events(connection))
    overall: dict[tuple[str, str, str], dict[str, Any]] = defaultdict(
        lambda: {"id": "", "events": 0, "actual": 0, "expected": 0.0, "comparisons": 0}
    )
    matchups: dict[tuple[str, str, str, str, str], dict[str, Any]] = defaultdict(
        lambda: {"id": "", "events": 0, "actual": 0, "expected": 0.0, "comparisons": 0}
    )
    for event in expected:
        ball = event.ball
        base_key = (ball.batter_name, ball.match_format, ball.competition)
        matchup_key = (*base_key, ball.phase, ball.bowling_type)
        for bucket in (overall[base_key], matchups[matchup_key]):
            bucket["id"] = ball.batter_id
            bucket["events"] += 1
            bucket["actual"] += ball.batter_runs
            bucket["expected"] += event.expected_runs
            bucket["comparisons"] += event.comparator_events

    overall_rows = []
    for (name, match_format, competition), value in overall.items():
        events = value["events"]
        if not events:
            continue
        above = value["actual"] - value["expected"]
        comparison_mean = round(value["comparisons"] / events)
        overall_rows.append([
            name, value["id"], match_format, competition, events, value["actual"], value["expected"], above,
            100 * above / events, comparison_mean, _evidence_level(events, comparison_mean),
        ])
    if overall_rows:
        connection.executemany(
            "INSERT INTO player_context_value_memory VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", overall_rows
        )

    matchup_rows = []
    for (name, match_format, competition, phase, bowling_type), value in matchups.items():
        events = value["events"]
        if not events:
            continue
        above = value["actual"] - value["expected"]
        comparison_mean = round(value["comparisons"] / events)
        matchup_rows.append([
            name, value["id"], match_format, competition, phase, bowling_type, events, value["actual"],
            value["expected"], above, 100 * above / events, comparison_mean,
            _evidence_level(events, comparison_mean),
        ])
    if matchup_rows:
        connection.executemany(
            "INSERT INTO player_context_matchup_memory VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", matchup_rows
        )
    _refresh_delivery_pattern_memory(connection, expected)


def _refresh_delivery_pattern_memory(
    connection: duckdb.DuckDBPyConnection, expected: list[ExpectedBall],
) -> None:
    """Persist only commentary patterns that link unambiguously to a ball."""
    supported_categories = {"length", "line", "variation"}
    tags_by_delivery: dict[tuple[str, int, int], list[tuple[str, str]]] = defaultdict(list)
    linked_deliveries: set[tuple[str, int, int]] = set()
    for match_id, innings_number, delivery_index, category, value in connection.execute(
        """SELECT l.match_id, l.innings_number, l.delivery_index, t.tag_category, t.tag_value
           FROM commentary_links l
           LEFT JOIN commentary_tags t ON t.source_file = l.source_file AND t.row_number = l.row_number
           WHERE l.link_status = 'linked' AND l.delivery_index IS NOT NULL"""
    ).fetchall():
        linked_deliveries.add((match_id, int(innings_number), int(delivery_index)))
        if category in supported_categories:
            tags_by_delivery[(match_id, int(innings_number), int(delivery_index))].append((category, value))

    available: dict[tuple[str, str, str, str, str, str], dict[str, int]] = defaultdict(
        lambda: {"events": 0, "linked": 0}
    )
    tagged: dict[tuple[str, str, str, str, str, str, str], dict[str, Any]] = defaultdict(
        lambda: {"id": "", "events": 0, "actual": 0, "expected": 0.0, "comparisons": 0}
    )
    for event in expected:
        ball = event.ball
        base = (ball.batter_name, ball.match_format, ball.competition, ball.phase, ball.bowling_type)
        is_linked = (ball.match_id, ball.innings_number, ball.delivery_index) in linked_deliveries
        for category in supported_categories:
            available[(*base, category)]["events"] += 1
            available[(*base, category)]["linked"] += int(is_linked)
        for category, value in tags_by_delivery.get(
            (ball.match_id, ball.innings_number, ball.delivery_index), []
        ):
            bucket = tagged[(*base, category, value)]
            bucket["id"] = ball.batter_id
            bucket["events"] += 1
            bucket["actual"] += ball.batter_runs
            bucket["expected"] += event.expected_runs
            bucket["comparisons"] += event.comparator_events

    rows = []
    for key, value in tagged.items():
        name, match_format, competition, phase, bowling_type, category, tag_value = key
        events = value["events"]
        coverage = available[(name, match_format, competition, phase, bowling_type, category)]
        all_events = coverage["events"]
        linked_events = coverage["linked"]
        above = value["actual"] - value["expected"]
        comparison_mean = round(value["comparisons"] / events)
        rows.append([
            name, value["id"], match_format, competition, phase, bowling_type, category, tag_value,
            events, all_events, linked_events, 100 * linked_events / all_events, 100 * events / all_events,
            value["actual"], value["expected"], above,
            100 * above / events, comparison_mean, _evidence_level(events, comparison_mean),
        ])
    if rows:
        # DuckDB's row-at-a-time executemany becomes prohibitively slow for
        # the many player × phase × type × pattern combinations.  Registering
        # one in-memory frame retains the same local-only data flow but makes
        # a refresh a bulk database operation.
        frame = pd.DataFrame(rows, columns=[
            "batter_name", "batter_id", "match_format", "competition", "phase", "bowling_type",
            "tag_category", "tag_value", "tagged_events", "available_events", "commentary_linked_events",
            "commentary_link_coverage_pct", "tag_share_pct",
            "batter_runs", "expected_batter_runs", "runs_above_expected", "runs_above_expected_per_100",
            "comparator_events", "evidence_level",
        ])
        connection.register("_pattern_memory_rows", frame)
        try:
            connection.execute(
                """INSERT INTO player_delivery_pattern_memory (
                       batter_name, batter_id, match_format, competition, phase, bowling_type,
                       tag_category, tag_value, tagged_events, available_events, commentary_linked_events,
                       commentary_link_coverage_pct, tag_share_pct, batter_runs, expected_batter_runs,
                       runs_above_expected, runs_above_expected_per_100, comparator_events, evidence_level
                   ) SELECT batter_name, batter_id, match_format, competition, phase, bowling_type,
                            tag_category, tag_value, tagged_events, available_events, commentary_linked_events,
                            commentary_link_coverage_pct, tag_share_pct, batter_runs, expected_batter_runs,
                            runs_above_expected, runs_above_expected_per_100, comparator_events, evidence_level
                   FROM _pattern_memory_rows"""
            )
        finally:
            connection.unregister("_pattern_memory_rows")


def player_contextual_value(
    connection: duckdb.DuckDBPyConnection, player_name: str, *, match_format: str = "T20",
    competition: str = "Indian Premier League",
) -> dict[str, Any]:
    """Return a transparent player card for downstream explanation/UI code."""
    overall = connection.execute(
        """SELECT * FROM player_context_value_memory
           WHERE batter_name = ? AND match_format = ? AND competition = ?""",
        [player_name, match_format, competition],
    ).fetchdf()
    if overall.empty:
        raise ValueError(f"No context-adjusted {match_format} {competition} memory for {player_name!r}.")
    columns = {row[1] for row in connection.execute(
        "PRAGMA table_info('player_context_matchup_memory')"
    ).fetchall()}
    comparator_column = "comparator_events" if "comparator_events" in columns else "exact_context_events"
    matchups = connection.execute(
        f"""SELECT phase, bowling_type, non_wide_events, batter_runs, expected_batter_runs,
                    runs_above_expected, runs_above_expected_per_100,
                    {comparator_column} AS comparator_events, evidence_level
             FROM player_context_matchup_memory
             WHERE batter_name = ? AND match_format = ? AND competition = ?
             ORDER BY runs_above_expected_per_100 ASC, non_wide_events DESC""",
        [player_name, match_format, competition],
    ).fetchdf()
    overall_card = overall.iloc[0].to_dict()
    if "exact_context_events" in overall_card:
        overall_card["comparator_events"] = overall_card.pop("exact_context_events")
    return {"overall": overall_card, "matchups": matchups.to_dict("records")}


def player_delivery_patterns(
    connection: duckdb.DuckDBPyConnection, player_name: str, *, match_format: str = "T20",
    competition: str = "Indian Premier League", minimum_events: int = 30,
) -> list[dict[str, Any]]:
    """Return commentary-supported patterns, ordered from lowest RAE upward."""
    rows = connection.execute(
        """SELECT phase, bowling_type, tag_category, tag_value, tagged_events, available_events,
                  commentary_linked_events, commentary_link_coverage_pct, tag_share_pct,
                  batter_runs, expected_batter_runs, runs_above_expected,
                  runs_above_expected_per_100, comparator_events, evidence_level
           FROM player_delivery_pattern_memory
           WHERE batter_name = ? AND match_format = ? AND competition = ? AND tagged_events >= ?
           ORDER BY runs_above_expected_per_100 ASC, tagged_events DESC""",
        [player_name, match_format, competition, minimum_events],
    ).fetchdf()
    return rows.to_dict("records")


def main() -> int:
    """Refresh or inspect the model without coupling it to the web UI."""
    parser = argparse.ArgumentParser(description="Query CricketIQ context-adjusted batting value.")
    parser.add_argument("--db", default=DEFAULT_DB_PATH)
    parser.add_argument("--player", help="Exact Cricsheet player name")
    parser.add_argument("--format", default="T20")
    parser.add_argument("--competition", default="Indian Premier League")
    parser.add_argument("--refresh", action="store_true", help="Rebuild contextual-value memory from local deliveries")
    parser.add_argument("--patterns", action="store_true", help="Return commentary-backed delivery patterns")
    args = parser.parse_args()
    if not args.refresh and not args.player:
        parser.error("provide --player to inspect a card, or --refresh to rebuild model memory")
    connection = connect(args.db, read_only=not args.refresh)
    try:
        if args.refresh:
            refresh_contextual_value_memory(connection)
            print("Context-adjusted player memory refreshed.")
        if args.player:
            result: Any = player_delivery_patterns(
                connection, args.player, match_format=args.format, competition=args.competition,
            ) if args.patterns else player_contextual_value(
                connection, args.player, match_format=args.format, competition=args.competition,
            )
            print(json.dumps(result, indent=2, default=str))
    finally:
        connection.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
