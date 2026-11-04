# Cricinfo commentary collector

Downloads ball-by-ball commentary for ESPNcricinfo matches, using the same
play-by-play feed that Cricinfo's "Commentary" tab loads. For each match it
walks every innings and page, then saves:

- `<match_id>.csv` with one row per delivery (bowler, batter, runs, wicket,
  running score, commentary text);
- `<match_id>.raw.json` with the untouched API responses, so the data can be
  reprocessed later; and
- `all_matches.csv`, which combines every match when you scrape more than one.

## What this is for

This is the data layer of an **AI Cricket Analyst**: a tool meant to answer
questions like "How do you get this batter out?" or "Why did India lose this
match?" and back every answer with the deliveries and commentary behind it.
Scorecards show *what* happened; the aim is to explain *why*, show the
evidence and say how confident the answer is.

Two design rules shape it:

- **Code does the maths, the model does the explaining.** Statistics come from
  deterministic Python. A language model only interprets evidence it is given,
  and cites the match, over and ball for every claim.
- **Honest uncertainty.** Answers carry sample sizes and say what cannot be
  concluded.

**Status:** the collection layer (this repository) is built and checked:
every innings' delivery count is matched against the feed's own count, and
final scores against official results. The analysis layer is designed but not
built yet; its first milestone is one end-to-end opposition report for a
single batter in T20Is.

**Known limitation:** format is inferred from the innings ball limit (120 =
T20, 300 = ODI), so rain-reduced matches with other limits are skipped by
`--formats`. The fix is to read the format from the match metadata.

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

`series_id, match_id, match_label, innings, innings_label, batting_team, over,
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
