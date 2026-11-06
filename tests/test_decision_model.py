from datetime import date
import json

from cricketiq.decision_model import CalibratedStateOdds, ChaseState, load_odi_chase_states, validate_on_holdout


def _match(target: int, winner: str, date_text: str) -> dict:
    return {
        "info": {"dates": [date_text], "overs": 2, "outcome": {"winner": winner}},
        "innings": [
            {"team": "A", "overs": []},
            {"team": "B", "target": {"runs": target, "overs": 2}, "overs": [
                {"over": 0, "deliveries": [
                    {"runs": {"total": 1}}, {"runs": {"total": 1}}, {"runs": {"total": 1}},
                    {"runs": {"total": 1}}, {"runs": {"total": 1}}, {"runs": {"total": 1}},
                ]},
            ]},
        ],
    }


def test_states_are_time_locked_and_exclude_future_matches(tmp_path) -> None:
    (tmp_path / "old.json").write_text(json.dumps(_match(20, "B", "2025-01-01")), encoding="utf-8")
    (tmp_path / "future.json").write_text(json.dumps(_match(20, "A", "2025-02-01")), encoding="utf-8")
    states = load_odi_chase_states(tmp_path, before=date(2025, 2, 1))
    assert len(states) == 1
    assert states[0].match_id == "old"
    assert states[0].score == 6
    assert states[0].balls_remaining == 6
    assert states[0].won is True


def test_odds_shrink_thin_neighbourhoods_away_from_certainty() -> None:
    history = [
        ChaseState(f"m{index}", date(2025, 1, 1), 300, 220, 5, 60, index < 8)
        for index in range(10)
    ]
    estimate = CalibratedStateOdds(history, minimum_states=1).estimate(history[0])
    assert 0.5 < estimate.chase_win_probability < 1.0
    assert estimate.lower_80 < estimate.chase_win_probability < estimate.upper_80


def test_validation_requires_a_meaningful_holdout_before_state_odds_are_approved() -> None:
    history = [ChaseState(f"h{index}", date(2025, 1, 1), 300, 220, 5, 60, index % 2 == 0) for index in range(40)]
    holdout = [ChaseState(f"v{index}", date(2025, 2, 1), 300, 220, 5, 60, index % 2 == 0) for index in range(10)]
    report = validate_on_holdout(CalibratedStateOdds(history, minimum_states=1), holdout)
    assert report.evaluated_states == 10
    assert report.ready_for_state_odds is False
