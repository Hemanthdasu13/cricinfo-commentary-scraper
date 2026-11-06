# Analysis system: research and plan

How cricket analysts slice ball-by-ball data, what we can and can't do with the
data we hold, and how to build our own system. Written 5 Nov 2026.

## 1. What the analysts do

### Himanish Ganjoo (Deep Point, all 23 posts read)

Ganjoo is a physicist who worked as an analyst with the Indian men's team. The
ideas worth borrowing:

- **Compare with the average player in the same situation, never with raw
  numbers.** His Runs Above Average gives each ball's runs minus the average for
  that wickets-down, phase and ground, then converts the season total to Wins
  Above Average. CricViz's Impact and Cricketingview's measures work the same way.
  How well you define "the same situation" decides how good the metric is.
- **Matchup indices against a baseline.** He published numbers sliced by
  batting hand, bowling type and innings phase. Each player is measured against
  the average player in that same matchup, not on raw strike rate.
- **Individual batter-v-bowler prediction is mostly noise.** He tried
  multiplying the two players' indices to predict a pairing, and it didn't hold
  up. Type-level matchups (batter v left-arm orthodox) are reliable; named pairs
  rarely have enough balls.
- **Measure the process, not just the result.** False shots, control and
  boundary attempts describe skill better than runs and outs over small samples.
  His T20 boundary model treats every ball as "attacked or not". Attacking gives
  far more runs but an 11% dismissal rate, against 2% when not attacking. He
  then simulates chases with Monte Carlo.
- **Conditions shift everything.** IPL scoring rose sharply with the Impact
  Player rule (from 2023) and flatter pitches. A good-length powerplay strike
  rate went from about 120 to 150 in three years. Splits need a season/era
  dimension, and IPL numbers don't transfer directly to internationals.
- **Shot variety (entropy).** Using wagon-wheel zones, he measures how many
  scoring options a batter has (entropy), and how unusual they are
  (KL divergence against the average batter for the same line and length).
- **Ball-tracking work** (slower-ball dip and pace loss, pitch bounce and turn,
  "misbehaving" balls, Axar Patel's release angle) needs Hawk-Eye data. That
  isn't public, so it's out of reach for us. His slower-ball cut-off was a speed
  (under 125 to 128 kph).

### Others

- Bowler-type labels everyone uses (ESPNcricinfo style): right/left-arm fast,
  fast-medium, medium; off-break, leg-break, slow left-arm orthodox, left-arm
  wrist spin.
- A Liverpool John Moores University study of 23,084 elite spin deliveries found batter-bowler handedness
  matchups significantly change runs conceded. Earlier work ignored handedness.
- ESPNcricinfo's matchup coverage splits by phase: powerplay 1-6, middle 7-15,
  death 16-20.

## 2. Every split you asked for, and whether we can do it

Measured on 81,136 IPL deliveries already downloaded.

| Split | Source | Coverage | Verdict |
|---|---|---|---|
| Batter right/left hand | ESPN player profile (`batStyle`) | every player | **Yes** |
| Bowler arm and type: pace v spin, fast/fast-medium/medium, off-break, leg-break, left-arm orthodox, left-arm wrist | ESPN player profile (`bowlStyle`) | every player | **Yes** |
| Phase (powerplay, middle, death) | over number | every ball | **Yes** |
| Innings, target, required rate, wickets down | Cricsheet / feed | every ball | **Yes** |
| Venue, season, Impact Player era | Cricsheet / summary | every ball | **Yes** |
| Length (yorker, full, good, short, bouncer) | commentary words | 66% of balls | **Partly**, flagged as text-derived |
| Line (outside off, at the stumps, pads, wide) | commentary words | 41% | **Partly** |
| Shot played (drive, pull, sweep, scoop) | commentary words | 23% | **Partly** |
| False shot (edge, beaten, miscue) | commentary words | 13% | **Partly**, a lower bound |
| Slower ball / cutter / knuckle ball | commentary words | 7% | **Partly** |
| Ball speed: 140+ kph v below | speed in commentary | **5%** | **Not per ball.** Per bowler: class a bowler as express from his typical mentioned speed, given enough mentions |
| Spin speed: 90+ v below | speed in commentary | rarer still for spin | **Per bowler at best**, and weak |
| Over or round the wicket | commentary | **0.5%** | **No** |

The splits we can do fully (hand, bowler type, arm, phase, situation, venue,
era) are the ones Ganjoo and published matchup work rely on most.

## 3. The system

**Layer 1: one ball table.** One row per delivery, joining three sources:

1. **Cricsheet** for clean outcomes (runs, extras, wickets, batter, bowler,
   non-striker) in every league and international.
2. **ESPN commentary** (our scraper) for the text-derived tags: length, line,
   shot, false shot, slower ball, mentioned speed.
3. **Player attributes** from the ESPN player profile: batting hand, bowling
   arm and type.

Join keys: Cricsheet's people register gives each player's Cricinfo ID, which is
also ESPN's. Matches are joined on date and teams.

**Layer 2: tags.** Phase, bowler kind, batter hand, era. Text tags carry a
"from commentary" flag, so they're never mixed silently with complete fields.

**Layer 3: metrics per slice.** Balls, runs, strike rate, dismissals, balls per
dismissal, dot %, boundary %, false-shot % where known. Then, our own versions
of the baseline ideas:

- **Expected runs per ball** for each situation (phase, wickets, innings, era,
  venue), and every player's runs above or below it.
- **Matchup index:** a player's rate against a bowling type, divided by
  everyone's rate against that type in the same phase.
- **Sample-size shrinkage** (independent of Ganjoo): blend thin samples towards
  the baseline. For example, add 60 "average" balls to every split, so 20
  explosive balls don't look like a trend. Always show the ball count.

**Layer 4: questions.** A query such as "Abhishek Sharma v left-arm orthodox,
powerplay, IPL since 2023" returns the numbers, the sample size and the
confidence. This is the evidence the fan-facing prompts in the README need.

## 4. Build order

1. Download Cricsheet's people register, and fetch batting and bowling styles
   for every player in the data (one request per player, cached).
2. Build the ball table from Cricsheet for IPL, BBL, SA20, The Hundred, CPL and
   the top-10 internationals since 2021.
3. Add phase, era and style tags; compute baselines and the matchup index.
4. Join commentary tags for the matches we've scraped.
5. Check a few results against published figures before trusting the system.

## Sources

- [Deep Point, Himanish Ganjoo](https://deeppoint.substack.com)
- [Leg spin or off spin, orthodox or unorthodox (LJMU)](https://researchonline.ljmu.ac.uk/id/eprint/27042/)
- [ESPNcricinfo: stats analysis](https://www.espncricinfo.com/ci/content/story/1258833.html)
- [Cricsheet](https://cricsheet.org)
