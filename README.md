# Cricinfo commentary collector

Downloads ball-by-ball commentary for ESPNcricinfo matches, using the same
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

## Collected so far

The NZ in India 2025-26 T20I series (India won 4-1), 1,148 deliveries. The
scraped files are git-ignored (the commentary is ESPNcricinfo's content). Run
the `--from-file` command above to regenerate them in
`data/ind_vs_nz_t20i_2026/`.

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
