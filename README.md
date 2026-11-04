# AI Cricket Insights: the data layer

This repository collects the historical ball-by-ball data behind a
**conversational cricket companion**. The idea is an app that watches the match
situation, spots a matchup that history has an opinion on, and tells the fan
what to look out for *before* it happens:

> **Watch this over.** Abhishek Sharma strikes at 270 against left-arm orthodox
> spin, and a left-arm spinner is coming on. Expect some big hits.
>
> *(An example of the intended output. The figure is illustrative; it has not
> been computed from this data yet.)*

When the over plays out the way the app said, the fan sees the pattern for
themselves. That is the point: it makes watching more interesting, and every
call can be checked.

## How the predictions get sharper

1. **Basic matchups.** Batter against bowler type: left-arm orthodox, wrist
   spin, right-arm pace and so on, split by phase of the innings. Many of these
   confirm what fans already sense, such as how a batter handles spin turning
   into or away from them; the value is putting a number and a sample size on
   it.
2. **Finer conditions.** Pace band, length and match situation. For example:
   against short balls above 140 kph, this batter's average drops sharply. The
   feed has no speed or length field, so both are read from the commentary
   text, which gives a speed for roughly one ball in nine and describes the
   length far more often.
3. **Live prompts.** When the live situation matches a pattern (a wicket falls,
   a fast bowler starts going short at 145 kph), the app raises it before the
   next ball.
4. **Conversation.** A fan can ask, "Is bringing on the left-arm spinner a good
   idea here?" and get an answer with the evidence, the sample size and how
   confident it is.

## Design rules

- **Code does the maths, the model does the talking.** Every number comes from
  deterministic Python over the data. A language model only turns that
  evidence into conversation, and cites the matches and deliveries behind it.
- **A prediction is a probability, not a promise.** Each call carries its
  sample size, and thin evidence is said to be thin.
- **Calls are scored.** Every prediction is logged and compared with what
  happened, so the app's hit rate is known rather than assumed.
- **For fans, not punters.** It is an engagement and explanation product, not
  a betting tool.

## Why the method travels

The core question is a prediction from history: will this batter get out, or
hit a six, in this over? Swap the batter for a customer and the over for a
product, and it is a question a bank asks every day: from this customer's past
transactions, how likely are they to buy this product? The steps are the same:
collect the history, find the patterns that hold up, predict, then check each
prediction against what actually happened. Cricket is the test domain because
the data is rich, public and changes ball by ball.

## Status

| Layer | State |
|---|---|
| Ball-by-ball collection from ESPNcricinfo (this repository) | **Built.** India since Nov 2023: 159 completed internationals found automatically; 120 ODIs and T20Is collected, 37,512 deliveries. The two 2026 T20I series were checked: every innings' delivery count against the feed's own count, and final scores against official results. |
| Match data from Cricbuzz | Planned, not started |
| Bowler types (pace or spin, arm, finger or wrist) | Planned, not started |
| Speed and length read from commentary text | Planned, not started |
| Matchup statistics, live prompts and the conversation layer | Designed, not built |

**Known limitation:** format is inferred from the innings ball limit (120 =
T20, 300 = ODI), so rain-reduced matches with other limits are skipped by
`--formats`, and 3 of the 37,512 deliveries above carry the wrong `format`
label. The fix is to read the format from the match metadata.

## What the collector does

It downloads ball-by-ball commentary for ESPNcricinfo matches, using the same
play-by-play feed that Cricinfo's "Commentary" tab loads. For each match it
walks every innings and page, then saves:

- `<match_id>.csv` with one row per delivery (bowler, batter, runs, wicket,
  running score, commentary text);
- `<match_id>.raw.json` with the untouched API responses, so the data can be
  reprocessed later; and
- `all_matches.csv`, which combines every match when you scrape more than one.

## Setup

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

## Use

One or more match URLs (any Cricinfo match page URL works):

```powershell
.venv\Scripts\python cricinfo_commentary.py "https://www.espncricinfo.com/series/new-zealand-in-india-2025-26-1490228/india-vs-new-zealand-5th-t20i-1490238/ball-by-ball-commentary"
```

A whole series from a URL list (one URL per line, `#` comments allowed):

```powershell
.venv\Scripts\python cricinfo_commentary.py --from-file matches/ind_vs_nz_t20i_2026.txt --output-dir data/ind_vs_nz_t20i_2026
```

Options: `--output-dir` (default `data`) and `--delay` seconds between requests
(default 1.5).

### Finding every match for a team and year

You don't have to build match lists by hand. `find_matches.py` builds one for a
team's whole year:

```powershell
.venv\Scripts\python find_matches.py --team-id 6 --year 2026 --out matches/india_2026.txt
.venv\Scripts\python cricinfo_commentary.py --from-file matches/india_2026.txt --output-dir data/india_2026
```

Use a date range instead of a year, and keep only some formats:

```powershell
.venv\Scripts\python find_matches.py --team-id 6 --start 2023-11-20 --out matches/india_since_wc2023.txt
.venv\Scripts\python cricinfo_commentary.py --from-file matches/india_since_wc2023.txt --formats odi,t20 --output-dir data/india_since_wc2023_odi_t20i
```

`--formats` (`t20`, `odi`, `test`) is detected from Cricinfo's data (the 120 or
300 ball limit per innings). A match in another format is skipped after one
request. Every CSV row also has a `format` column.

Cricinfo's own website blocks automated requests, so the fixture list comes
from ESPN.com (`espn.com/cricket/scores/team/<id>`). ESPN owns Cricinfo and the
match IDs are identical. The commentary itself still comes from Cricinfo's
feed. The script:

- reads one page per month and falls back to day-by-day pages when ESPN returns
  an error for a month, then retries any failed days more slowly;
- keeps completed matches only; and
- skips non-competitive games by default: `--exclude "sixes,warm-up,tour match"`.

It warns and exits with code 1 if any day still can't be fetched, so a gap is
never silent. Team IDs are in ESPN URLs (India 6, NZ 5, Australia 2, England 1).

## Collected so far

The scraped files are git-ignored (the commentary is ESPNcricinfo's content).
Run `--from-file` with the matching list in `matches/` to regenerate them.

### India, all completed ODIs and T20Is, 20 Nov 2023 to 3 Nov 2026

List: `matches/india_since_wc2023.txt` (159 completed internationals, found
by `find_matches.py`). Output: `data/india_since_wc2023_odi_t20i/`: 120
matches, 37,512 deliveries. The other 39 were skipped as other formats: the
Tests, plus rain-reduced games caught by the known limitation above.

### India in New Zealand 2026-27, 5 T20Is (India won 3-2)

List: `matches/ind_in_nz_t20i_2026.txt`. Output: `data/ind_in_nz_t20i_2026/`
(1,209 deliveries).

| Match | ID | Venue | Result | Deliveries |
|---|---|---|---|---|
| 1st T20I | 1539432 | Christchurch | NZ 225/4, IND 230/6 (19.4): India by 4 wkts | 254 |
| 2nd T20I | 1539433 | Christchurch | NZ 180/5, IND 181/6 (19.5): India by 4 wkts | 254 |
| 3rd T20I | 1539434 | Wellington | NZ 198/3, IND 199/4 (13.2): India by 6 wkts | 212 |
| 4th T20I | 1539435 | Auckland | NZ 259/7, IND 172/9: NZ by 87 runs | 253 |
| 5th T20I | 1539436 | Hamilton | IND 191/8, NZ 195/3 (18): NZ by 7 wkts | 236 |

### New Zealand in India 2025-26, 5 T20Is (India won 4-1)

List: `matches/ind_vs_nz_t20i_2026.txt`. Output: `data/ind_vs_nz_t20i_2026/`
(1,148 deliveries).

| Match | ID | Result | Deliveries |
|---|---|---|---|
| 1st T20I | 1490234 | IND 238/7, NZ 190/7 | 252 |
| 2nd T20I | 1490235 | NZ 208/6, IND 209/3 (15.2) | 227 |
| 3rd T20I | 1490236 | NZ 153/9, IND 155/2 (10) | 183 |
| 4th T20I | 1490237 | NZ 215/7, IND 165 all out | 238 |
| 5th T20I | 1490238 | IND 271/5, NZ 225 all out | 248 |

## CSV columns

`series_id, match_id, match_label, format, innings, innings_label, batting_team, over,
over_number, ball_in_over, bowler, batter, non_striker, runs, play_type,
is_wicket, dismissal_type, dismissal_text, innings_runs, innings_wickets,
target, short_text, text, pre_text, post_text, timestamp_ms, sequence`

`text` holds the ball commentary. `pre_text` and `post_text` hold the
between-ball notes (team news, end-of-over remarks), with HTML stripped.

## Notes

- The feed is undocumented and can change. It also returns sporadic HTTP 502s;
  the script retries those with backoff.
- Keep the request delay in place and don't use this for high-volume
  collection. Commentary text belongs to ESPNcricinfo, so check that your use
  is permitted by its terms before redistributing the data.

## Licence

Copyright © 2026 Hemanth Dasu. All rights reserved. The code is public so it
can be read and reviewed; no licence is granted to copy, modify or
redistribute it.
