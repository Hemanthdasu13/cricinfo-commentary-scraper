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

**The product is called CricBuddy.** The idea, a real example computed from
this data, how it will be built and where each part stands are in
[docs/CRICBUDDY.md](docs/CRICBUDDY.md).

The first product slice is an **ODI chase situation lab**: a user enters the
target, score, wickets and balls remaining, then sees a time-locked historical
estimate with its uncertainty and supporting sample. It is deliberately narrow
and does not make player-level or captaincy recommendations yet.

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
| Ball-by-ball collection from ESPNcricinfo (this repository) | **Built.** Top-10 teams' head-to-head ODIs and T20Is since Nov 2023: 426 matches, 144,375 deliveries. India since Nov 2023: 159 completed internationals found automatically; 120 ODIs and T20Is collected, 37,512 deliveries. 2021+ T20 leagues: in progress. The two 2026 T20I series were checked: every innings' delivery count against the feed's own count, and final scores against official results. |
| Match data from Cricbuzz | Planned, not started |
| Bowler types (pace or spin, arm, finger or wrist) | Planned, not started |
| Speed and length read from commentary text | Planned, not started |
| Matchup statistics, live prompts and the conversation layer | Designed, not built |

**Fixed (4 Nov 2026):** format used to be inferred from the innings ball
limit (120 = T20, 300 = ODI), so rain-reduced matches were wrongly skipped by
`--formats`. It is now read from the match summary's official match class. The
end-of-match notes item the feed adds is also no longer saved as a delivery.

## What the collector does

It downloads ball-by-ball commentary for ESPNcricinfo matches, using the same
play-by-play feed that Cricinfo's "Commentary" tab loads. For each match it
walks every innings and page, then saves:

- `<match_id>.csv` with one row per delivery (bowler, batter, runs, wicket,
  running score, commentary text);
- `<match_id>.raw.json` with the untouched API responses, so the data can be
  reprocessed later;
- `<match_id>.summary.json` with the match summary (format, teams, venue,
  result, playing XIs); and
- `all_matches.csv`, which combines every match when you scrape more than one.

If a match's `.raw.json` is already in the output folder, it is reused rather
than downloaded again. Re-runs only fetch what's missing, and a CSV can be
rebuilt with the latest code at no cost.

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

`--formats` (`t20`, `odi`, `test`) is read from the match summary's official
match class, so rain-reduced games are still recognised (their `ball_limit`
column shows the reduced overs). A match in another format is skipped after
one request. Every CSV row also has a `format` column.

### Several teams, head-to-head only

```powershell
.venv\Scripts\python find_matches.py --team-id 1,2,3,4,5,6,7,8,25,40 --head-to-head --start 2023-11-20 --out matches/top10_h2h.txt --others-out matches/top10_vs_others.txt
.venv\Scripts\python cricinfo_commentary.py --from-file matches/top10_h2h.txt --formats odi,t20 --teams 1,2,3,4,5,6,7,8,25,40 --output-dir data/top10_h2h_odi_t20i
```

`--head-to-head` keeps only matches between two of the listed teams. A match
counts if it shows up in two of the teams' fixture lists or both team names are
in its URL. Matches against anyone else are written to `--others-out` so they
can be collected later if needed. In the scraper, `--teams` checks both sides
against the match summary and skips anything else.

Cricinfo's own website blocks automated requests, so the fixture list comes
from ESPN.com (`espn.com/cricket/scores/team/<id>`). ESPN owns Cricinfo and the
match IDs are identical. The commentary itself still comes from Cricinfo's
feed. The script:

- reads one page per month and falls back to day-by-day pages when ESPN returns
  an error for a month, then retries any failed days more slowly;
- keeps completed matches only; and
- skips non-competitive games by default: `--exclude "sixes,warm-up,tour match"`.

It warns and exits with code 1 if any day still can't be fetched, so a gap is
never silent. Team IDs are in ESPN URLs: England 1, Australia 2, South Africa 3, West
Indies 4, New Zealand 5, India 6, Pakistan 7, Sri Lanka 8, Zimbabwe 9,
Bangladesh 25, Ireland 29, Afghanistan 40.

### Every match on a range of days (leagues and internationals)

```powershell
.venv\Scripts\python find_matches.py --daily --series-ids 8048,8044,8679,8623,19601,21275,20921,21266 --team-id 1,2,3,4,5,6,7,8,25,40 --head-to-head --start 2021-01-01 --out matches/t20_since_2021.txt
.venv\Scripts\python cricinfo_commentary.py --from-file matches/t20_since_2021.txt --formats t20,hundred --output-dir data/t20_since_2021
```

`--daily` reads ESPN's all-cricket page for each day (`/cricket/scores?date=`)
instead of team pages. ESPN's per-season league pages only show part of a
season (IPL 2023 showed 32 of 74 games), so the daily pages are the complete
source. A match is kept if its series ID is in `--series-ids`, or, with
`--head-to-head`, if both teams in its URL are in `--team-id`. ESPN's regional
sites (africa.espn.com, espn.com.au and others) have separate caches, so a day
that fails with HTTP 503 on one is tried on the next.

League IDs, the same every season: IPL 8048, Big Bash 8044, PSL 8679, CPL 8623,
The Hundred men's 19601 (women's 21376), SA20 21275, ILT20 20921, Major League
Cricket 21266.

League games are classed "Twenty20" rather than "T20I"; both count as `t20`,
and the `match_class` column tells them apart. The Hundred is given its own
format, `hundred`, so its 100-ball innings stay out of T20 figures. Its feed
numbers balls in sets of five, so an `over` of `18.5` is the 95th ball.

## Collected so far

The scraped files are git-ignored (the commentary is ESPNcricinfo's content).
Run `--from-file` with the matching list in `matches/` to regenerate them.

### India, all completed ODIs and T20Is, 20 Nov 2023 to 3 Nov 2026

List: `matches/india_since_wc2023.txt` (159 completed internationals, found
by `find_matches.py`). Output: `data/india_since_wc2023_odi_t20i/`: 120
matches, 37,512 deliveries. The other 39 were skipped as other formats: 34
Tests, plus 5 rain-reduced games caught by the since-fixed format bug. Four of
those five are head-to-heads and are collected in the top-10 run below.

### Top 10 teams, head-to-head ODIs and T20Is, 20 Nov 2023 to 4 Nov 2026

Teams: England, Australia, South Africa, West Indies, New Zealand, India,
Pakistan, Sri Lanka, Bangladesh, Afghanistan. Only matches between two of these
teams are included. List: `matches/top10_h2h.txt` (550 completed matches).
Their 210 matches against other teams are listed in
`matches/top10_vs_others.txt` but not collected. Output:
`data/top10_h2h_odi_t20i/`.

| | Matches | Deliveries |
|---|---|---|
| T20I | 262 | 58,803 |
| ODI | 164 | 85,572 |
| **Total** | **426** | **144,375** |

The other 124 in the list: 109 Tests (skipped by `--formats`) and 15 matches
with no ball-by-ball commentary, almost all washouts. 45 of the collected
matches were rain-reduced. Checked: every match is between two of the ten
teams (from the summary's team IDs), and no ball appears twice.

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

`series_id, match_id, match_label, format, match_class, ball_limit, innings, innings_label,
batting_team, over, over_number, ball_in_over, bowler, bowler_id, batter,
batter_id, non_striker, non_striker_id, runs, play_type, is_wicket,
dismissal_type, dismissal_text, innings_runs, innings_wickets, target,
short_text, text, pre_text, post_text, timestamp_ms, sequence`

`text` holds the ball commentary. `pre_text` and `post_text` hold the
between-ball notes (team news, end-of-over remarks), with HTML stripped. The
`*_id` columns are Cricinfo player IDs, which stay stable even when a name is
spelled differently. `match_class` is the official class from the match
summary (`T20I`, `ODI`, `Twenty20` for league games). Older outputs (the India folders) predate `ball_limit`
and the ID columns; re-run with the same list to rebuild them from the saved
raw data without downloading again.

The feed also adds an end-of-match notes item (presentation quotes, wrap-up).
It isn't a delivery, so it stays in the raw JSON and not in the CSV.

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
