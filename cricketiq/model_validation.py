"""Time-based validation for CricketIQ's context-adjusted baseline.

Evaluation is deliberately chronological: rates are fit using only completed
seasons before a cutoff, then used to score later balls.  This is a check on
whether the context definition improves a simple phase baseline; it is not a
claim that single-ball outcomes are predictable.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import asdict, dataclass
import json

import duckdb

from cricketiq.config import DEFAULT_DB_PATH
from cricketiq.contextual_value import ContextBall, _context_keys, _events
from cricketiq.database import connect


MIN_TRAINING_EVENTS = 100


@dataclass(frozen=True)
class TemporalValidationReport:
    """Out-of-time, per-ball squared-error and calibration summary."""

    cutoff_season: str
    training_events: int
    test_events: int
    model_coverage: float
    model_mean_squared_error: float
    phase_mean_squared_error: float
    model_mean_error: float
    phase_mean_error: float
    recency_model_mean_squared_error: float
    recency_model_mean_error: float


def _fit_rates(
    events: list[ContextBall], *, detailed: bool, recency_half_life_seasons: float | None = None,
) -> dict[tuple[object, ...], tuple[float, float]]:
    totals: dict[tuple[object, ...], list[float]] = defaultdict(lambda: [0.0, 0.0])
    seasons = [int(ball.season) for ball in events if ball.season.isdigit()]
    newest_season = max(seasons) if seasons else 0
    for ball in events:
        weight = 1.0
        if recency_half_life_seasons and ball.season.isdigit():
            weight = 0.5 ** ((newest_season - int(ball.season)) / recency_half_life_seasons)
        keys = _context_keys(ball, include_bowling_type=True) if detailed else (
            (ball.match_format, ball.competition, ball.phase),
            (ball.match_format, ball.phase),
        )
        for key in keys:
            totals[key][0] += weight
            totals[key][1] += weight * ball.batter_runs
    return {key: (count, runs / count) for key, (count, runs) in totals.items() if count}


def _prediction(
    ball: ContextBall, rates: dict[tuple[object, ...], tuple[int, float]], *, detailed: bool,
) -> float | None:
    keys = _context_keys(ball, include_bowling_type=True) if detailed else (
        (ball.match_format, ball.competition, ball.phase),
        (ball.match_format, ball.phase),
    )
    fallback: float | None = None
    for key in keys:
        count, rate = rates.get(key, (0, 0.0))
        if count:
            fallback = rate
        if count >= MIN_TRAINING_EVENTS:
            return rate
    return fallback


def validate_by_season(
    connection: duckdb.DuckDBPyConnection, cutoff_season: str,
) -> TemporalValidationReport:
    """Train before ``cutoff_season`` and evaluate on it and later seasons."""
    events = _events(connection)
    training = [event for event in events if event.season and event.season < str(cutoff_season)]
    testing = [event for event in events if event.season and event.season >= str(cutoff_season)]
    if not training or not testing:
        raise ValueError("The requested cutoff must leave both earlier training and later test events.")
    model_rates = _fit_rates(training, detailed=True)
    # This value is fixed before inspecting the held-out result: evidence from
    # two IPL seasons back receives half the influence of the latest season.
    recency_rates = _fit_rates(training, detailed=True, recency_half_life_seasons=2.0)
    phase_rates = _fit_rates(training, detailed=False)
    model_errors: list[float] = []
    phase_errors: list[float] = []
    model_residuals: list[float] = []
    phase_residuals: list[float] = []
    recency_errors: list[float] = []
    recency_residuals: list[float] = []
    for ball in testing:
        model = _prediction(ball, model_rates, detailed=True)
        recency = _prediction(ball, recency_rates, detailed=True)
        phase = _prediction(ball, phase_rates, detailed=False)
        if model is not None:
            model_errors.append((ball.batter_runs - model) ** 2)
            model_residuals.append(ball.batter_runs - model)
        if phase is not None:
            phase_errors.append((ball.batter_runs - phase) ** 2)
            phase_residuals.append(ball.batter_runs - phase)
        if recency is not None:
            recency_errors.append((ball.batter_runs - recency) ** 2)
            recency_residuals.append(ball.batter_runs - recency)
    return TemporalValidationReport(
        cutoff_season=str(cutoff_season),
        training_events=len(training),
        test_events=len(testing),
        model_coverage=len(model_errors) / len(testing),
        model_mean_squared_error=sum(model_errors) / len(model_errors),
        phase_mean_squared_error=sum(phase_errors) / len(phase_errors),
        model_mean_error=sum(model_residuals) / len(model_residuals),
        phase_mean_error=sum(phase_residuals) / len(phase_residuals),
        recency_model_mean_squared_error=sum(recency_errors) / len(recency_errors),
        recency_model_mean_error=sum(recency_residuals) / len(recency_residuals),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate CricketIQ's context baseline on later seasons.")
    parser.add_argument("--db", default=DEFAULT_DB_PATH)
    parser.add_argument("--cutoff-season", default="2025")
    args = parser.parse_args()
    connection = connect(args.db, read_only=True)
    try:
        print(json.dumps(asdict(validate_by_season(connection, args.cutoff_season)), indent=2))
    finally:
        connection.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
