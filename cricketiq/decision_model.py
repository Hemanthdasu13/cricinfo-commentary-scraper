"""Time-locked, calibrated baseline odds for limited-overs chase decisions.

This module deliberately separates *state odds* from a recommendation about a
specific bowling change.  The latter needs much richer batter/bowler/conditions
evidence and must not be inferred from the eventual result of the match under
review.  The state model is therefore useful as a calibrated control: any
future plan simulator must beat it out-of-sample before its counterfactual
figures are shown to a user.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class ChaseState:
    """A pre-delivery snapshot from the second innings of an ODI chase."""

    match_id: str
    match_date: date
    target: int
    score: int
    wickets: int
    balls_remaining: int
    won: bool

    @property
    def runs_required(self) -> int:
        return max(self.target - self.score, 0)

    @property
    def required_rate(self) -> float:
        return 6 * self.runs_required / self.balls_remaining if self.balls_remaining else math.inf


@dataclass(frozen=True)
class OddsEstimate:
    """A transparent, local-neighbour estimate of the chasing side's chance."""

    chase_win_probability: float
    effective_sample_size: float
    nearest_states: int
    lower_80: float
    upper_80: float


@dataclass(frozen=True)
class ValidationReport:
    """Held-out forecast quality used to gate fan-facing recommendations."""

    evaluated_states: int
    brier_score: float
    reference_brier_score: float
    mean_predicted_win_probability: float
    observed_win_rate: float

    @property
    def beats_reference(self) -> bool:
        return self.brier_score < self.reference_brier_score

    @property
    def ready_for_state_odds(self) -> bool:
        # This deliberately does not approve a player-level bowling-change
        # recommendation.  That needs its own plan-level backtest.
        return self.evaluated_states >= 250 and self.beats_reference


def _legal_delivery(delivery: dict) -> bool:
    extras = delivery.get("extras") or {}
    return "wides" not in extras and "noballs" not in extras


def _wicket_count(delivery: dict) -> int:
    # Retired hurt is not a wicket; the other listed wickets consume a batter.
    return sum(1 for wicket in delivery.get("wickets") or [] if wicket.get("kind") != "retired hurt")


def _match_states(path: Path, *, before: date | None = None) -> list[ChaseState]:
    """Extract only information knowable at each stored state.

    Cricsheet's target field handles revised targets, so rain-affected matches
    are not silently treated as 50-over first-innings-plus-one chases.
    """
    try:
        match = json.loads(path.read_text(encoding="utf-8"))
        info = match["info"]
        match_date = date.fromisoformat(info["dates"][0])
        innings = match.get("innings") or []
        if len(innings) < 2 or "target" not in innings[1]:
            return []
        target = int(innings[1]["target"]["runs"])
        max_balls = int(innings[1]["target"].get("overs", info.get("overs", 50))) * 6
        chasing_team = innings[1]["team"]
        winner = (info.get("outcome") or {}).get("winner")
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return []
    if before is not None and match_date >= before:
        return []
    if winner not in {chasing_team, innings[0].get("team")}:
        return []

    won = winner == chasing_team
    score = wickets = legal_balls = 0
    states: list[ChaseState] = []
    for over in innings[1].get("overs") or []:
        for delivery in over.get("deliveries") or []:
            score += int((delivery.get("runs") or {}).get("total", 0))
            wickets += _wicket_count(delivery)
            if _legal_delivery(delivery):
                legal_balls += 1
            remaining = max_balls - legal_balls
            # End-over and wicket snapshots are actual decision points; states
            # after the target is reached are excluded from model training.
            if score < target and remaining > 0 and (
                legal_balls % 6 == 0 or delivery.get("wickets")
            ):
                states.append(ChaseState(path.stem, match_date, target, score, wickets, remaining, won))
    return states


def load_odi_chase_states(
    directory: Path | str,
    *,
    before: date | None = None,
    minimum_match_id: int | None = None,
) -> list[ChaseState]:
    """Load reproducible ODI chase snapshots from a Cricsheet directory."""
    paths = sorted(Path(directory).glob("*.json"))
    if minimum_match_id is not None:
        paths = [path for path in paths if path.stem.isdigit() and int(path.stem) >= minimum_match_id]
    return [state for path in paths for state in _match_states(path, before=before)]


class CalibratedStateOdds:
    """Distance-weighted empirical odds with a conservative beta prior.

    It is intentionally non-parametric.  The query can expose its neighbour
    count and uncertainty instead of presenting a fragile single fitted number.
    """

    def __init__(self, states: Iterable[ChaseState], *, minimum_states: int = 50) -> None:
        self.states = tuple(states)
        self.minimum_states = minimum_states

    @staticmethod
    def _distance(left: ChaseState, right: ChaseState) -> float:
        # Scales were selected as cricket-relevant neighbourhood widths, rather
        # than tuned on the match being assessed.
        return (
            ((left.required_rate - right.required_rate) / 1.15) ** 2
            + ((left.balls_remaining - right.balls_remaining) / 30) ** 2
            + ((left.wickets - right.wickets) / 1.25) ** 2
            + ((left.target - right.target) / 90) ** 2
        )

    def estimate(self, state: ChaseState) -> OddsEstimate:
        if len(self.states) < self.minimum_states:
            raise ValueError(f"Need at least {self.minimum_states} historic states; found {len(self.states)}")
        ranked = sorted(
            ((self._distance(state, prior), prior) for prior in self.states),
            key=lambda item: item[0],
        )[:250]
        # A broad prior avoids 100% claims from a thin slice.  The effective
        # sample size is shown so callers can gate recommendations.
        weights = [math.exp(-distance / 2) for distance, _ in ranked]
        total_weight = sum(weights)
        weighted_wins = sum(weight for weight, (_, prior) in zip(weights, ranked) if prior.won)
        alpha = 5 + weighted_wins
        beta = 5 + total_weight - weighted_wins
        probability = alpha / (alpha + beta)
        variance = probability * (1 - probability) / (alpha + beta + 1)
        spread = 1.28155 * math.sqrt(variance)
        effective_n = total_weight * total_weight / sum(weight * weight for weight in weights)
        return OddsEstimate(
            chase_win_probability=probability,
            effective_sample_size=effective_n,
            nearest_states=len(ranked),
            lower_80=max(0.0, probability - spread),
            upper_80=min(1.0, probability + spread),
        )


def brier_score(model: CalibratedStateOdds, states: Iterable[ChaseState]) -> float:
    """Evaluate probabilities on a holdout set; lower is better (0 is perfect)."""
    outcomes = [(model.estimate(state).chase_win_probability, state.won) for state in states]
    if not outcomes:
        raise ValueError("No holdout states supplied")
    return sum((probability - int(won)) ** 2 for probability, won in outcomes) / len(outcomes)


def validate_on_holdout(
    model: CalibratedStateOdds,
    holdout: Iterable[ChaseState],
    *,
    maximum_states: int = 400,
) -> ValidationReport:
    """Score a temporal holdout without letting it influence the model.

    One evenly spaced snapshot is taken from each section of the holdout when
    a corpus is large.  It keeps validation fast and avoids a single long chase
    dominating the score with dozens of strongly correlated states.
    """
    candidates = list(holdout)
    if not candidates:
        raise ValueError("No holdout states supplied")
    if len(candidates) > maximum_states:
        step = len(candidates) / maximum_states
        candidates = [candidates[int(index * step)] for index in range(maximum_states)]
    probabilities = [model.estimate(state).chase_win_probability for state in candidates]
    observed = [int(state.won) for state in candidates]
    baseline = sum(int(state.won) for state in model.states) / len(model.states)
    return ValidationReport(
        evaluated_states=len(candidates),
        brier_score=sum((probability - outcome) ** 2 for probability, outcome in zip(probabilities, observed))
        / len(candidates),
        reference_brier_score=sum((baseline - outcome) ** 2 for outcome in observed) / len(candidates),
        mean_predicted_win_probability=sum(probabilities) / len(probabilities),
        observed_win_rate=sum(observed) / len(observed),
    )
