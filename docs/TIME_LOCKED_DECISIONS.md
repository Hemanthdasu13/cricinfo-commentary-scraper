# Time-locked decision odds

`cricketiq.decision_model` provides a conservative baseline for assessing a
limited-overs chase at the moment of a captaincy decision.

It uses only Cricsheet matches dated before the state under review.  Each
historical observation is an end-of-over or wicket state from a second-innings
ODI chase.  The comparable features are required rate, balls remaining,
wickets down and target.  The output is a distance-weighted empirical chase
win probability with an 80% uncertainty interval and an effective neighbour
count.

This module intentionally does **not** claim that a named bowler should have
bowled a particular over.  A player-level plan simulator requires a separate
out-of-sample validated outcome model, plus enough data for the named matchup.
The rule is:

> A counterfactual bowling-plan advantage is not shown unless it is larger
> than its uncertainty and improves held-out calibration.

Example:

```python
from datetime import date
from cricketiq.decision_model import CalibratedStateOdds, ChaseState, load_odi_chase_states

history = load_odi_chase_states("data/cricsheet/odis_male", before=date(2026, 10, 31))
model = CalibratedStateOdds(history)
state = ChaseState("1550719", date(2026, 10, 31), 326, 230, 5, 79, False)
print(model.estimate(state))
```

The `won` value on the query state is ignored; it exists only because a
`ChaseState` can also represent a labelled historical observation.  This keeps
the pre-decision and evaluation representations identical.

## Validation gate

`validate_on_holdout` scores the model only on later, unseen states and reports
the Brier score against a constant historical-win-rate reference.  State odds
are not approved unless they improve on that reference over at least 250
held-out snapshots.  This is intentionally only a gate for *state* odds: a
named bowling-plan recommendation remains blocked until its own counterfactual
simulator has passed an equivalent time-split backtest.
