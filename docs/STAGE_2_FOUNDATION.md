# CricketIQ Stage 2: local foundation

The source data under `data/` is treated as read-only. The importer creates a generated DuckDB database at `data/processed/cricketiq.duckdb`.

## Starter import

This imports the 426 local IPL matches that have both Cricsheet and commentary coverage, plus the available player-style table:

```powershell
.\.venv\Scripts\python.exe -m cricketiq.ingest
```

## Full local import

After the starter import has been checked, import every local source directory:

```powershell
.\.venv\Scripts\python.exe -m cricketiq.ingest --all
```

## Run the interface

```powershell
.\.venv\Scripts\streamlit.exe run app.py
```

## What is stored

- `matches`, `innings`, `deliveries`: normalised Cricsheet facts;
- `commentary_matches`, `commentary_records`: original normalised commentary fields, including original text;
- `match_players`: each Cricsheet match's players with their Cricsheet and Cricinfo IDs, from Cricsheet's people register (`data/cricsheet/people.csv`);
- `commentary_links`: delivery links only when match ID, innings, ball label, batter, bowler, and runs yield exactly one candidate, and no other commentary record claims the same delivery. Batter and bowler are compared by Cricinfo ID, because the sources spell names differently ("JA Duffy" in Cricsheet, "Jacob Duffy" in the commentary); exact names are used only when a side has no ID. A wide or no-ball is labelled by the legal balls already bowled in the commentary ("14.0") and by the next legal ball in Cricsheet ("14.1"), so an extra may match the next label when both sources call it an extra. On the 426 IPL matches, 100,026 of 102,027 commentary records (98.0%) link;
- `players`: existing player-style output; and
- `validation_issues`: visible import problems, rather than silent omissions. A match found in more than one commentary folder is imported once, from the first folder, and each repeat is recorded here.

The first import intentionally handles a smaller overlapping corpus. That keeps the first Player Intelligence feature reproducible while the full archive remains available for later expansion.

## Player-memory layer

Every successful import refreshes a query-ready Player Intelligence memory layer:

- personal batting baselines by format and competition;
- player-versus-bowling-type profiles, ranked against that player's own baseline;
- commentary tags for explicit length, line, variation, and shot phrases; and
- source-preserving dismissal examples and repeated tactical signals.

For linked records, it also stores exact batter outcomes by each commentary tag
and by a length-plus-line combination. That is the layer used to spot patterns
such as a batter being contained to singles by a hard length around off stump;
it is not limited to dismissal analysis.

The query returns three complementary views: the primary vulnerability score
(suppression, dismissal risk, and sample reliability combined), greatest
scoring suppression, and highest wicket risk. Keeping them separate stops a
small but dramatic dismissal split from being presented as a player's complete
weakness.

It uses a 60-event empirical prior to shrink thin samples toward the player's
overall baseline. A bowling type must have at least 50 non-wide delivery events
and three bowler-attributable dismissals before it is eligible to be called a
potential vulnerability. A line, length, variation, or shot pattern also needs
two tagged dismissals and at least 35% of the tagged evidence. This prevents a
single memorable dismissal becoming a claimed weakness.

Query a profile without rescanning the raw archive:

```powershell
.\.venv\Scripts\python.exe -m cricketiq.player_memory "Abhishek Sharma"
```
