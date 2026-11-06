# Context-adjusted player value

This model is CricketIQ's first Deep Point-inspired performance layer.  It is
not a model that tells a captain what *should* have happened in a particular
over, and it does not predict a named batter-versus-bowler duel.

## Method

For every non-wide delivery, the importer records only information available
before the ball:

- format and competition;
- first innings or chase;
- phase (T20: overs 1–6, 7–15, 16+; ODI: 1–10, 11–40, 41+);
- wickets already lost (capped at five);
- current score in ten-run bands; and
- bowler's broad type from the player-style source.

For each ball it finds a pool of **other batters** in the same state and type.
It backs off, transparently, from score-band + wickets to wickets, then phase,
then format + phase.  It uses the first pool with at least 100 other-batter
events.  The focal batter's whole contribution is subtracted from every pool,
so a great innings cannot inflate that player's own benchmark.

`RAE = actual batter runs − expected batter runs`

The model stores RAE overall and by phase × bowling type, together with balls
faced, the mean comparison-pool size, and an evidence label.  The main query is
`cricketiq.contextual_value.player_contextual_value`.

## Commentary-backed delivery patterns

`player_delivery_patterns` adds a separate, narrower read model for `length`,
`line`, and `variation` tags.  It includes a ball only when source commentary
is uniquely linked to the Cricsheet delivery.  The same contextual expected
score is then attached to the tagged ball.

Every row displays three distinct quantities: `commentary_link_coverage_pct`
(the share of eligible source balls with a uniquely linked commentary record),
`tag_share_pct` (the share specifically classified as that pattern), and
`tagged_events`.  A missing tag is not a claim that the delivery was not full,
short, or outside off.  This is essential: commentary describes only a subset
of balls in those technical terms.

Use `python -m cricketiq.contextual_value --player "Name" --patterns` to inspect
this layer.  It defaults to a 30-tag minimum, which is still labelled limited
evidence below 50 tagged balls.

## Interpretation

This follows Himanish Ganjoo's framing of impact-style measures: compare output
with an average player in the same situation rather than treating raw strike
rate as ability.  It also follows his explicit caution that type-level matchup
summaries are more reliable than named batter–bowler predictions because the
latter are small-sample and high-variance.

The result is a player-memory foundation such as: “against left-arm orthodox in
the IPL middle overs, this batter scored X runs above/below the comparable
other-batter expectation over N balls.”  It is **not** evidence for: “this
named spinner will dismiss this batter,” or “use this bowling change.”

## Deliberate limits

Cricsheet ball-by-ball data does not contain tracked line, length, pace, shot
zone, field placement, or control percentage.  Therefore this model makes no
claim such as “full and wide outside off” from delivery outcomes alone.  Those
claims remain commentary-supported hypotheses until a separate tracking-data
model and held-out validation are available.

The 100-event comparator threshold and 50-ball player evidence threshold are
product guardrails, not universal cricket constants.  They are shown alongside
the result and can be re-tuned only after temporal holdout validation.

## Source methodology

- Himanish Ganjoo, [Measuring T20](https://www.deeppoint-hg.com/p/measuring-t20): context-adjusted output, the value of process measures, and the named-matchup small-sample warning.
- Himanish Ganjoo, [Quantifying Option Versatility in T20s](https://www.deeppoint-hg.com/p/quantifying-option-versatility-in): the useful counterfactual pattern of comparing a batter with the average batter facing the same balls.
- Himanish Ganjoo, [The Effect of Misbehaving Balls on T20 Scoring](https://www.deeppoint-hg.com/p/the-effect-of-misbehaving-balls-on): an example of constructing runs-above-expected at ball level and checking context/era features.
