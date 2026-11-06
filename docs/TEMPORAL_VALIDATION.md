# Temporal validation: contextual run baseline

## Protocol

The test trains the baseline on IPL seasons before 2025 (2021–24) and evaluates
every non-wide batter event in 2025–26.  It is compared with a deliberately
simple alternative that knows only format, competition, and phase.  Neither
model sees the held-out seasons while fitting rates.

## Result on the local IPL corpus

| Measure | Context + bowling type | Phase-only | Context + type + 2-season recency |
| --- | ---: | ---: |
| Training events | 64,785 | 64,785 | 64,785 |
| Held-out events | 33,255 | 33,255 | 33,255 |
| Coverage | 100% | 100% | 100% |
| Per-ball mean squared error | 3.41835 | 3.41862 | **3.40952** |
| Mean residual (actual − expected) | +0.1638 | +0.1597 | **+0.1324** |

The pre-declared two-season recency weighting improves the held-out error and
reduces, but does not remove, the underprediction of the more aggressive
2025–26 environment.  It is therefore the preferred historical baseline for a
future forecasting experiment, but it has not passed the much higher bar for a
betting input or tactical recommender.  The stored RAE model remains a
transparent **retrospective normaliser**.

Run the check locally:

```powershell
.\.venv\Scripts\python.exe -m cricketiq.model_validation --cutoff-season 2025
```

## Gate for the next model

Before a simulator or captaincy recommendation can use player effects, we need
a time-aware model that materially improves held-out calibration, plus a
separate decision-policy evaluation.  The current result fails that gate.
