# Handover: AI Cricket Insights / CricketIQ

Written 5 Nov 2026 for whoever picks this project up next, starting with Codex.
It covers what exists, how to run it, what the data sources do, and what's
left. Read sections 1 and 2 before changing anything.

## 1. Owner's rules (keep these)

- **The project's own Python code does the collecting.** The owner needs to be
  able to say their tool scraped the data, not an AI.
- **Never delete old records.** Add to match lists and data; don't overwrite or
  remove them.
- **Commit or push only when the owner asks.** The GitHub repo is public:
  https://github.com/Hemanthdasu13/cricinfo-commentary-scraper. Code only.
  `data/` is git-ignored and must stay out, because the commentary is
  ESPNcricinfo's content.
- **Don't get around blocking.** Use the script's own User-Agent
  (`Mozilla/5.0 (commentary-research-collector/1.1)`). No browser User-Agents,
  proxies or tricks. If ESPN refuses requests, back off and try later.
- **Be polite to ESPN.** Wait at least 1.5 s between requests, and run only
  one bulk download at a time.
- **Evidence first** (the app's rule): the database retrieves, Python
  calculates, and AI only explains. Never present a number without its sample
  size.

## 2. Status at a glance

| Piece | State |
|---|---|
| Commentary scraper (`cricinfo_commentary.py`) | Working. Every download below is complete. |
| Match finders (`find_matches.py`, `find_season_matches.py`) | Working. |
| Player styles (`player_styles.py`) | Complete: 1,173 players, all matched. |
| Cricsheet ball-by-ball files | Downloaded 5 Nov 2026 (latest at that time). |
| CricketIQ app (`app.py`, `cricketiq/`) | Stage 2 foundation built. IPL imported: 98.0% of commentary balls linked to Cricsheet. Player-memory layer added. 6 tests pass. |
| Other leagues' commentary (BBL, SA20, The Hundred, CPL) | **Complete** (7 Nov 2026): BBL 288, SA20 130, CPL 200, The Hundred 201 matches. Every Cricsheet match since 2021 has commentary. |
| All commentary together | 2,099 matches and 582,998 deliveries (top-10 head-to-heads, IPL and the four leagues, not counting the overlapping India folder). |
| Coverage check against Cricsheet (since 2021) | Top-10 T20Is 446/446 and ODIs 314/314 have commentary. IPL 426/427: the missing one, PBKS v DC on 8 May 2025, was abandoned after 63 balls, and ESPN doesn't serve it (summary 404, feed 500). |
| Git | **Nothing from this phase is committed.** See section 10. |

## 3. Environment

- Windows 11. Python 3.12 virtual environment in `.venv`
  (`.venv\Scripts\python.exe`).
- `requirements.txt`: requests, duckdb, streamlit, plotly, pytest.
- GitHub CLI (if needed):
  `C:\Users\hddas\AppData\Local\Microsoft\WinGet\Packages\GitHub.cli_Microsoft.Winget.Source_8wekyb3d8bbwe\bin\gh.exe`
- Long downloads stop when the laptop sleeps. Keep it plugged in, with sleep
  set to Never, for anything over an hour.

## 4. What's in the folder

| Path | What it is |
|---|---|
| `cricinfo_commentary.py` | Downloads ball-by-ball commentary for a list of match URLs. Writes per-match CSV, raw JSON and summary JSON, plus `all_matches.csv`. Reuses saved raw files, so re-runs only fetch what's missing. |
| `find_matches.py` | Builds a match list from ESPN.com schedule pages: by team and month (`--team-id`, `--head-to-head`), or day by day (`--daily`). |
| `find_season_matches.py` | Builds a match list for whole league seasons from ESPN's JSON API, using each season's series ID. This is how the IPL list was built. |
| `matches_from_cricsheet.py` | Builds a match list from a folder of Cricsheet files. Cricsheet names files by Cricinfo match ID, and ESPN's feed accepts the league's constant series ID, so no ESPN search is needed. Used for BBL, SA20, CPL and The Hundred. |
| `player_styles.py` | Batting hand and bowling type for every player in a set of Cricsheet matches, from ESPN player profiles. |
| `app.py` | Streamlit front end for CricketIQ (data-status page). |
| `cricketiq/` | CricketIQ package: `config.py`, `database.py` (DuckDB schema), `ingest.py` (importer and linking), `player_memory.py` (player-intelligence layer). |
| `tests/` | pytest suite and small fixture files. |
| `docs/STAGE_2_FOUNDATION.md` | CricketIQ's own documentation: tables, linking rules, player-memory rules. |
| `matches/*.txt` | Match lists, one URL per line, `#` comments. Inputs for the scraper. Keep them all. |
| `README.md` | Public project description. The owner rewrote the top; keep their wording. |
| `ANALYSIS_PLAN.md` | Research on how analysts slice ball-by-ball data (including Himanish Ganjoo's Deep Point posts) and the analysis-system plan. |
| `PROJECT_AND_RESUME.md` | Private notes on the project and résumé wording (git-ignored). Its "known issues" are out of date: both have since been fixed. |
| `data/` | All downloaded and generated data (git-ignored). See section 5. |
| `.test-tmp/`, `pytest-cache-files-*/`, `r.out` | Leftovers from test runs. Safe to ignore; all git-ignored. |

## 5. Data inventory (`data/`, local only)

### Commentary (from the ESPNcricinfo feed)

Each folder has `<match_id>.csv`, `<match_id>.raw.json`,
`<match_id>.summary.json` (newer folders only) and `all_matches.csv`.

| Folder | Content | Matches | Deliveries | List |
|---|---|---|---|---|
| `top10_h2h_2021_2023/` | Top-10 head-to-head ODIs and T20Is, 1 Jan 2021 to 19 Nov 2023 | 427 | 154,804 | `matches/top10_h2h_2021_2023.txt` |
| `top10_h2h_odi_t20i/` | Top-10 head-to-head ODIs and T20Is, 20 Nov 2023 to 4 Nov 2026 | 427 | 144,762 | `matches/top10_h2h.txt` |
| `ipl_2021_2026/` | IPL, all six seasons 2021 to 2026 | 426 | 102,027 | `matches/ipl_2021_2026.txt` |
| `bbl_2021_2026/` | Big Bash League, 2020/21 to 2025/26 seasons (matches from 1 Jan 2021) | 288 | 66,676 | `matches/bbl_2021_2026.txt` |
| `sa20_2021_2026/` | SA20, 2023 to 2026 | 130 | 28,980 | `matches/sa20_2021_2026.txt` |
| `cpl_2021_2026/` | Caribbean Premier League, 2021 to 2026 | 200 | 46,972 | `matches/cpl_2021_2026.txt` |
| `hundred_2021_2026/` | The Hundred (men's), 2021 to 2026; format `hundred` | 201 | 38,777 | `matches/hundred_2021_2026.txt` |
| `india_since_wc2023_odi_t20i/` | India ODIs and T20Is since Nov 2023 (older CSV layout, no player IDs) | 120 | 37,512 | `matches/india_since_wc2023.txt` |
| `india_2026/`, `ind_in_nz_t20i_2026/`, `ind_vs_nz_t20i_2026/` | Earlier small test sets | | | matching files in `matches/` |

The top 10 are England, Australia, South Africa, West Indies, New Zealand,
India, Pakistan, Sri Lanka, Bangladesh and Afghanistan. "Head-to-head" means
both teams are from this group. Their matches against anyone else are listed
in `matches/top10_vs_others*.txt` but not downloaded; that was the owner's call.

Gaps in these sets are explained, not errors:
- Tests are excluded by `--formats odi,t20`.
- Washouts and called-off matches have no commentary: 17 in 2021–23, 15 since
  Nov 2023, and 4 in IPL.
- The NZ v India 1st ODI (4 Nov 2026, match 1539437) was added by hand at the
  end of `matches/top10_h2h.txt`, because it finished after the list was built.

### Cricsheet (`data/cricsheet/`)

Free ball-by-ball JSON from https://cricsheet.org/downloads/, downloaded 5 Nov
2026. Cricsheet's data is licensed ODC-BY, so credit Cricsheet when you use it.
Each file is named by its Cricinfo match ID.

| Folder | From zip | Seasons since 2021 |
|---|---|---|
| `ipl/` | `ipl_json.zip` | 60, 74, 74, 71, 74, 74 |
| `bbl/` | `bbl_json.zip` | 2020/21 to 2025/26 |
| `sat/` (SA20) | `sat_json.zip` | 2022/23 to 2025/26 |
| `hnd_male/` (The Hundred, men's) | `hnd_male_json.zip` | 2021 to 2026 |
| `cpl/` | `cpl_json.zip` | 2021 to 2026 |
| `t20s_male/`, `odis_male/` | men's T20Is and ODIs | all teams; filter to the top 10 yourself |
| `people.csv` | Cricsheet people register | Maps Cricsheet player IDs to Cricinfo IDs (`key_cricinfo`) |
| `zips/` | the original downloads | |

Cricsheet has no commentary, no bowler type and no ball speed.

### Players (`data/players/`)

- `player_styles.csv`: 1,173 players with `bat_hand`, `bowl_arm`, `bowl_kind`
  (pace or spin), `bowl_type` (fast, fast-medium, medium-fast, medium,
  off-break, leg-break, left-arm orthodox, left-arm wrist spin) and the raw ESPN
  text. Covers every player in the five leagues plus top-10 internationals
  since 2021.
- `athletes/<cricinfo_id>.json`: saved ESPN profiles. A re-run only fetches
  new players.

### Generated

- `processed/cricketiq.duckdb`: CricketIQ database. It's generated, so rebuild
  it with the importer at any time. It currently holds the IPL starter import.
- `*.log`: logs of every run.

## 6. How to run things

Run all commands from the project folder with the virtual environment's Python.

```powershell
# Find matches: one team, or several teams head-to-head
.venv\Scripts\python find_matches.py --team-id 6 --start 2026-10-20 --out matches/new_list.txt
.venv\Scripts\python find_matches.py --team-id 1,2,3,4,5,6,7,8,25,40 --head-to-head --start 2021-01-01 --end 2023-11-19 --out matches/top10_h2h_2021_2023.txt --others-out matches/top10_vs_others_2021_2023.txt

# Find matches: whole league seasons by season series ID (IPL 2021-2026 shown)
.venv\Scripts\python find_season_matches.py --season-ids 1249214,1298423,1345038,1410320,1449924,1510719 --out matches/ipl_2021_2026.txt

# Download commentary (re-running retries failures and reuses saved files)
.venv\Scripts\python -u cricinfo_commentary.py --from-file matches/ipl_2021_2026.txt --formats t20 --output-dir data/ipl_2021_2026
.venv\Scripts\python -u cricinfo_commentary.py --from-file matches/top10_h2h.txt --formats odi,t20 --teams 1,2,3,4,5,6,7,8,25,40 --output-dir data/top10_h2h_odi_t20i

# Player styles
.venv\Scripts\python player_styles.py --league-dirs data/cricsheet/ipl,data/cricsheet/bbl,data/cricsheet/sat,data/cricsheet/hnd_male,data/cricsheet/cpl --intl-dirs data/cricsheet/t20s_male,data/cricsheet/odis_male --since 2021-01-01 --delay 2

# CricketIQ
.venv\Scripts\python -m pytest -q
.venv\Scripts\python -m cricketiq.ingest              # IPL starter import
.venv\Scripts\python -m cricketiq.ingest --all        # everything in data/
.venv\Scripts\python -m cricketiq.player_memory "Abhishek Sharma"
.venv\Scripts\streamlit run app.py
```

If a download ends with "N match(es) FAILED", run the same command again. It
reuses saved files and retries only the failures. ESPN's 502 errors come and
go.

## 7. Data sources and their quirks

### The commentary feed (works reliably)

```
https://site.web.api.espn.com/apis/site/v2/sports/cricket/{series_id}/playbyplay?contentorigin=espn&event={match_id}&period={innings}&page=1&limit=1000&section=cricinfo
```

- `limit=1000` returns a whole innings in one request; the speed-up came from
  this.
- It keys on `event`, so a wrong series ID still works.
- An item with ID `"999999999999999"` (a string) holds end-of-match notes.
  It's not a delivery, and the scraper excludes it.
- It sometimes repeats a ball; the scraper removes duplicates by
  innings, item ID and sequence.
- Player IDs are included: `bowler.athlete.id` and `batsman.athlete.id`. These
  are Cricinfo IDs.
- It has no structured line, length or speed; those are only in the text.

### Match summary

`.../cricket/{series_id}/summary?event={match_id}` needs the right series ID
(404 otherwise). `header.competitions[0].class.generalClassCard` is the
official format: `T20I`, `ODI`, `Test`, or `Twenty20` for league games and The
Hundred. The scraper maps `Twenty20` to `t20`, and The Hundred (series 19601
men's, 21376 women's) to `hundred`. The format must come from here, not from
the ball limit: rain-reduced games were once skipped because of that.

### Season lists (JSON API, used by `find_season_matches.py`)

`.../cricket/{season_series_id}/scoreboard?dates=YYYYMMDD`

- A whole-month request (`dates=YYYYMM`) leaves some entries blank, so the
  script asks one day at a time.
- A day request can also come back with a blank entry. Asking again returns
  the match, so blank days are retried.
- Each league season has its own series ID: the number in a Cricinfo series
  URL, for example `ipl-2026-1510719`. These are separate from the constant
  league IDs.
- **IPL season IDs:** 2021 1249214, 2022 1298423, 2023 1345038,
  2024 1410320, 2025 1449924, 2026 1510719.
- **Constant league IDs:** IPL 8048, BBL 8044, PSL 8679, CPL 8623, The
  Hundred 19601 (women's 21376), SA20 21275, ILT20 20921, MLC 21266.

### ESPN.com schedule pages (fragile)

`https://www.espn.com/cricket/scores/team/{team_id}/{slug}?date=YYYYMM`, or the
daily all-cricket page `/cricket/scores?date=YYYYMMDD`.

- These return HTTP 503 for pages ESPN hasn't cached, and on 4 Nov 2026 they
  refused everything for several hours after heavy use.
- Season fixture pages show only part of a season (IPL 2023 showed 32 of 74),
  so don't use them.
- `find_matches.py --daily` rotates through ESPN's regional sites when a page
  fails. The owner wasn't asked about this, and it may count as working around
  a limit. Before relying on it, ask the owner or remove it (section 1).
- **Team IDs:** England 1, Australia 2, South Africa 3, West Indies 4, New
  Zealand 5, India 6, Pakistan 7, Sri Lanka 8, Zimbabwe 9, Bangladesh 25,
  Ireland 29, Afghanistan 40.

### Player profiles

`https://site.web.api.espn.com/apis/common/v3/sports/cricket/athletes/{cricinfo_id}`
returns `batStyle` and `bowlStyle` descriptions, for example
"Left-hand bat" and "Slow left-arm orthodox".

### Things not to use

- **Cricinfo's own website** blocks automated requests. Use the ESPN endpoints
  above; they serve the same data with the same IDs.
- **CricViz** is commercial, licensed data with no public download.

## 8. The CricketIQ app

The owner built this. In short:

- **Storage:** DuckDB at `data/processed/cricketiq.duckdb`. Cricsheet facts
  are in `matches`, `innings` and `deliveries`; commentary is in
  `commentary_matches` and `commentary_records`; player styles are in
  `players`.
- **Linking:** commentary is joined to Cricsheet one ball at a time in
  `commentary_links`. The rules, all in `cricketiq/ingest.py`:
  - Players are compared by **Cricinfo ID**, through the `match_players` table
    and the people register. Names differ between the sources: Cricsheet has
    "JA Duffy", the commentary has "Jacob Duffy". The old India files have no
    IDs, so they fall back to exact names.
  - **Wides and no-balls** are labelled by the legal balls already bowled in the
    commentary ("14.0") but by the next legal ball in Cricsheet ("14.1"). An
    extra may match the next label, but only when both sources call it an
    extra.
  - Runs must agree. A ball must have exactly one candidate, and links are
    one-to-one: if two commentary rows claim one delivery, both stay
    unresolved.
  - Result on IPL: **100,026 of 102,027 commentary balls linked (98.0%)**. The
    rest are left unresolved rather than guessed.
  - A match found in two commentary folders is imported once, and each repeat
    is recorded in `validation_issues`.
- **Player memory** (`cricketiq/player_memory.py`): personal baselines,
  player-v-bowling-type profiles with a 60-event shrinkage prior, commentary
  tags for length, line, variation and shot, and dismissal evidence. A type
  must have at least 50 deliveries and 3 dismissals before it can be called a
  vulnerability. The rules are in `docs/STAGE_2_FOUNDATION.md`.
- **Tests:** `tests/test_ingestion.py` (5 tests: ID linking, wides, duplicates,
  one-to-one) and `tests/test_player_memory.py` (1 test). All 6 pass.

## 9. What's left

1. **Commentary collection is complete** (7 Nov 2026). The BBL, SA20, CPL and
   The Hundred lists were built from Cricsheet with `matches_from_cricsheet.py`
   and checked against it: all 819 matches have commentary. To add new
   matches later, download Cricsheet's latest zip, rebuild the list with
   `matches_from_cricsheet.py`, and re-run the scraper. Saved matches are reused.
   Example:

   ```powershell
   .venv\Scripts\python -u cricinfo_commentary.py --from-file matches/bbl_2021_2026.txt --formats t20 --output-dir data/bbl_2021_2026
   .venv\Scripts\python -u cricinfo_commentary.py --from-file matches/hundred_2021_2026.txt --formats hundred --output-dir data/hundred_2021_2026
   ``` Cricsheet already has the
   ball-by-ball facts for all of them.
2. **Run `cricketiq.ingest --all`** once the data is in place, and check the
   link rate per competition. The internationals and the old India folder may
   need their own checks.
3. **Analysis splits** (see `ANALYSIS_PLAN.md`). Batting hand, bowler arm and
   type, phase, situation, venue and era are fully available. Length (on 66% of
   balls) and line (41%) come from commentary text. Ball speed appears on only
   5% of balls and over/round the wicket on 0.5%, so per-ball pace bands
   (140+ kph, spin 90+) aren't possible. Classify bowlers by their typical
   mentioned speed instead.
4. **README:** add the season method (`find_season_matches.py`), the player
   styles script, the IPL and 2021–23 datasets, and Cricsheet's licence note.
   Keep the owner's wording at the top.
5. **Fix `PROJECT_AND_RESUME.md`:** its known issues are fixed; add the new
   datasets.
6. **First product milestone (owner's idea, on hold):** a matchup report for
   Abhishek Sharma, for example how he scores against left-arm orthodox in the
   powerplay, with sample sizes.

## 10. Git state

- Branch `main`. Last commit: `afd1bc9` ("Draw the customer parallel and state
  the copyright").
- Uncommitted and modified: `.gitignore`, `README.md`,
  `cricinfo_commentary.py`, `find_matches.py`, `requirements.txt`.
- Untracked: `ANALYSIS_PLAN.md`, `HANDOVER.md`, `app.py`, `cricketiq/`,
  `docs/`, `find_season_matches.py`, `player_styles.py`, `pytest.ini`,
  `tests/`, and the new `matches/*.txt` lists.
- **Ask the owner before committing.** The match lists contain only URLs,
  which is fine to publish. Never commit `data/`.
