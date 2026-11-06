"""Import existing Cricsheet and commentary files into CricketIQ's DuckDB store.

This module never changes the source corpus. It reads JSON/CSV inputs and writes
only the generated database under ``data/processed`` by default.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import duckdb

from cricketiq.config import DATA_DIR, DEFAULT_DB_PATH, PROJECT_ROOT
from cricketiq.contextual_value import refresh_contextual_value_memory
from cricketiq.database import connect, status_rows
from cricketiq.player_memory import refresh_player_memory


COMMENTARY_COLUMNS = {
    "match_id", "innings", "over", "bowler", "batter", "non_striker", "runs",
    "is_wicket", "innings_runs", "innings_wickets", "text",
}


def json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True) if value else ""


def as_int(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    return int(float(value))


def as_bool(value: str | None) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes"}


def issue(connection: duckdb.DuckDBPyConnection, source: Path, kind: str, detail: str) -> None:
    connection.execute(
        "INSERT INTO validation_issues(source_path, issue_type, detail) VALUES (?, ?, ?)",
        [str(source), kind, detail],
    )


def load_register(path: Path | None) -> dict[str, str]:
    """Cricsheet person ID -> Cricinfo ID, from Cricsheet's people register."""
    if path is None or not path.exists():
        return {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return {
            row["identifier"]: row.get("key_cricinfo") or row.get("key_cricinfo_2") or ""
            for row in csv.DictReader(handle)
        }


def import_cricsheet_file(
    connection: duckdb.DuckDBPyConnection, path: Path, register: dict[str, str] | None = None
) -> int:
    """Upsert one official Cricsheet JSON file and return its delivery count."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        info = payload["info"]
        innings_data = payload["innings"]
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as error:
        issue(connection, path, "invalid_cricsheet_json", str(error))
        return 0

    match_id = path.stem
    teams = info.get("teams", [])
    if len(teams) != 2:
        issue(connection, path, "unexpected_teams", f"Expected two teams; received {teams!r}")
    dates = info.get("dates") or []
    match_date = dates[0] if dates else None
    event = info.get("event", {})
    connection.execute("DELETE FROM deliveries WHERE match_id = ?", [match_id])
    connection.execute("DELETE FROM innings WHERE match_id = ?", [match_id])
    connection.execute("DELETE FROM match_players WHERE match_id = ?", [match_id])
    people = info.get("registry", {}).get("people", {})
    if people:
        register = register or {}
        connection.executemany(
            "INSERT INTO match_players VALUES (?, ?, ?, ?)",
            [[match_id, name, person_id, register.get(person_id, "")] for name, person_id in people.items()],
        )
    connection.execute(
        """INSERT OR REPLACE INTO matches VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            match_id, match_date, event.get("name", ""), str(info.get("season", "")),
            info.get("match_type", ""), info.get("gender", ""), info.get("team_type", ""),
            json_text(teams), info.get("venue", ""), json_text(info.get("outcome")), str(path),
        ],
    )

    count = 0
    for innings_number, innings in enumerate(innings_data, start=1):
        batting_team = innings.get("team", "")
        running_runs = 0
        wickets = 0
        rows: list[list[Any]] = []
        delivery_index = 0
        for over in innings.get("overs", []):
            over_number = int(over.get("over", 0)) + 1
            for delivery in over.get("deliveries", []):
                delivery_index += 1
                runs = delivery.get("runs", {})
                total = int(runs.get("total", 0))
                running_runs += total
                wicket_data = delivery.get("wickets", [])
                wickets += len(wicket_data)
                rows.append([
                    match_id, innings_number, delivery_index, str(delivery.get("actual_delivery", "")),
                    over_number, delivery.get("batter", ""), delivery.get("bowler", ""),
                    delivery.get("non_striker", ""), int(runs.get("batter", 0)),
                    int(runs.get("extras", 0)), total, json_text(delivery.get("extras")),
                    json_text(wicket_data), str(path),
                ])
        if not batting_team:
            issue(connection, path, "missing_batting_team", f"Innings {innings_number}")
        connection.execute(
            "INSERT INTO innings VALUES (?, ?, ?, ?, ?, ?)",
            [match_id, innings_number, batting_team, running_runs, wickets, str(path)],
        )
        if rows:
            connection.executemany("INSERT INTO deliveries VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
            count += len(rows)
    return count


def import_commentary_file(connection: duckdb.DuckDBPyConnection, path: Path) -> int:
    """Import one normalised commentary CSV without changing its original text."""
    source_file = str(path.resolve())
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            columns = set(reader.fieldnames or [])
            missing = COMMENTARY_COLUMNS - columns
            if missing:
                issue(connection, path, "invalid_commentary_csv", f"Missing columns: {sorted(missing)}")
                return 0
            records = list(reader)
    except (OSError, UnicodeDecodeError, csv.Error) as error:
        issue(connection, path, "invalid_commentary_csv", str(error))
        return 0
    if not records:
        issue(connection, path, "empty_commentary_csv", "No delivery rows")
        return 0

    match_id = records[0].get("match_id", "")
    if not match_id or any(row.get("match_id", "") != match_id for row in records):
        issue(connection, path, "inconsistent_match_id", "Rows must contain one non-empty match_id")
        return 0

    connection.execute("DELETE FROM commentary_links WHERE source_file = ?", [source_file])
    connection.execute("DELETE FROM commentary_records WHERE source_file = ?", [source_file])
    connection.execute("DELETE FROM commentary_matches WHERE source_file = ?", [source_file])
    first = records[0]
    connection.execute(
        "INSERT INTO commentary_matches VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            source_file, match_id, first.get("series_id", ""), first.get("match_label", ""),
            first.get("format", ""), first.get("match_class", ""), as_int(first.get("ball_limit")), str(path),
        ],
    )
    rows = []
    for row_number, row in enumerate(records, start=1):
        over_text = row.get("over", "")
        try:
            over_number = as_int(row.get("over_number"))
            ball_in_over = as_int(row.get("ball_in_over"))
        except ValueError as error:
            issue(connection, path, "invalid_ball_number", f"row {row_number}: {error}")
            over_number, ball_in_over = None, None
        rows.append([
            source_file, row_number, match_id, as_int(row.get("innings")), over_text,
            over_number, ball_in_over, row.get("batting_team", ""), row.get("batter", ""),
            row.get("batter_id", ""), row.get("bowler", ""), row.get("bowler_id", ""),
            row.get("non_striker", ""), as_int(row.get("runs")), as_bool(row.get("is_wicket")),
            row.get("dismissal_type", ""), row.get("dismissal_text", ""),
            as_int(row.get("innings_runs")), as_int(row.get("innings_wickets")),
            as_int(row.get("target")), row.get("short_text", ""), row.get("text", ""),
            row.get("pre_text", ""), row.get("post_text", ""), as_int(row.get("timestamp_ms")),
            as_int(row.get("sequence")),
        ])
    connection.executemany(
        "INSERT INTO commentary_records VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    return len(rows)


def import_players(connection: duckdb.DuckDBPyConnection, path: Path) -> int:
    if not path.exists():
        return 0
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    connection.execute("DELETE FROM players")
    values = [[row.get(column, "") for column in (
        "cricsheet_id", "cricsheet_name", "cricinfo_id", "espn_name", "matches", "teams", "bat_hand",
        "bowl_arm", "bowl_kind", "bowl_type", "bat_style_raw", "bowl_style_raw", "status",
    )] for row in rows]
    connection.executemany("INSERT INTO players VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", values)
    return len(values)


def json_files(directories: Iterable[Path], match_ids: set[str] | None = None) -> Iterable[Path]:
    for directory in directories:
        for path in sorted(directory.glob("*.json")):
            if match_ids is None or path.stem in match_ids:
                yield path


def commentary_files(directories: Iterable[Path]) -> Iterable[Path]:
    for directory in directories:
        yield from sorted(path for path in directory.glob("*.csv") if path.name != "all_matches.csv")


def refresh_links(connection: duckdb.DuckDBPyConnection) -> None:
    """Create only unambiguous links; other rows remain visible as unresolved.

    Players are compared by Cricinfo ID when both sources have one, because the
    sources spell names differently ("JA Duffy" v "Jacob Duffy"). Rows without
    IDs on either side (older commentary files) fall back to exact names.
    """
    connection.execute("DELETE FROM commentary_links")
    connection.execute(
        """
        INSERT INTO commentary_links
        WITH ids AS (
            SELECT d.*, coalesce(mb.cricinfo_id, '') AS batter_cricinfo_id,
                   coalesce(mw.cricinfo_id, '') AS bowler_cricinfo_id
            FROM deliveries d
            LEFT JOIN match_players mb ON mb.match_id = d.match_id AND mb.player_name = d.batter
            LEFT JOIN match_players mw ON mw.match_id = d.match_id AND mw.player_name = d.bowler
        ),
        candidates AS (
            SELECT c.source_file, c.row_number, c.match_id, c.innings_number,
                   d.delivery_index,
                   count(d.delivery_index) OVER (PARTITION BY c.source_file, c.row_number) AS candidate_count,
                   (coalesce(c.batter_id, '') <> '' AND d.batter_cricinfo_id <> ''
                    AND coalesce(c.bowler_id, '') <> '' AND d.bowler_cricinfo_id <> '') AS by_id
            FROM commentary_records c
            LEFT JOIN ids d
              ON d.match_id = c.match_id
             AND d.innings_number = c.innings_number
             -- A wide or no-ball is labelled by the legal balls already bowled
             -- in the commentary ("14.0") but by the next legal ball in
             -- Cricsheet ("14.1"). Allow that shift only when both sources
             -- say the ball was an extra.
             AND (d.actual_delivery = c.over_text
                  OR (regexp_matches(lower(coalesce(c.short_text, '')), 'wide|no ball|no-ball')
                      AND (coalesce(d.extras_json, '') LIKE '%"wides"%'
                           OR coalesce(d.extras_json, '') LIKE '%"noballs"%')
                      AND d.actual_delivery = split_part(c.over_text, '.', 1) || '.'
                          || CAST(TRY_CAST(split_part(c.over_text, '.', 2) AS INTEGER) + 1 AS VARCHAR)))
             AND CASE WHEN coalesce(c.batter_id, '') <> '' AND d.batter_cricinfo_id <> ''
                      THEN d.batter_cricinfo_id = c.batter_id ELSE d.batter = c.batter END
             AND CASE WHEN coalesce(c.bowler_id, '') <> '' AND d.bowler_cricinfo_id <> ''
                      THEN d.bowler_cricinfo_id = c.bowler_id ELSE d.bowler = c.bowler END
             AND d.total_runs = c.runs
        )
        SELECT source_file, row_number, match_id, innings_number,
               CASE WHEN candidate_count = 1 THEN max(delivery_index) END,
               CASE WHEN candidate_count = 1 THEN 'linked' ELSE 'unresolved' END,
               candidate_count,
               CASE WHEN candidate_count <> 1
                    THEN 'No unique delivery match; retained without a forced link'
                    WHEN bool_and(by_id)
                    THEN 'match, innings, ball label, batter and bowler Cricinfo IDs, and runs agree'
                    ELSE 'match, innings, ball label, batter and bowler names, and runs agree' END
        FROM candidates
        GROUP BY source_file, row_number, match_id, innings_number, candidate_count
        """
    )
    # Links are one-to-one. If two commentary records each found the same single
    # delivery (a wide and a no-ball in one over, say), neither link is trusted.
    connection.execute(
        """
        UPDATE commentary_links
        SET link_status = 'unresolved', delivery_index = NULL,
            evidence = 'Another commentary record matched the same delivery; retained without a forced link'
        WHERE link_status = 'linked'
          AND (match_id, innings_number, delivery_index) IN (
              SELECT (match_id, innings_number, delivery_index) FROM commentary_links
              WHERE link_status = 'linked'
              GROUP BY match_id, innings_number, delivery_index HAVING count(*) > 1)
        """
    )


def default_paths(all_sources: bool) -> tuple[list[Path], list[Path]]:
    if all_sources:
        cricsheet = sorted(path for path in (DATA_DIR / "cricsheet").iterdir() if path.is_dir())
        commentary = sorted(
            path for path in DATA_DIR.iterdir()
            if path.is_dir() and path.name not in {"cricsheet", "players"}
        )
    else:
        cricsheet = [DATA_DIR / "cricsheet" / "ipl"]
        commentary = [DATA_DIR / "ipl_2021_2026"]
    return cricsheet, commentary


def run_import(
    database_path: Path,
    cricsheet_directories: Iterable[Path],
    commentary_directories: Iterable[Path],
    player_styles_path: Path,
    cricsheet_match_ids: set[str] | None = None,
    register_path: Path | None = None,
) -> dict[str, int]:
    connection = connect(database_path)
    register = load_register(register_path)
    # DuckDB is dramatically faster when the many small source files share one
    # transaction; it also prevents a half-import from being visible if a run fails.
    connection.execute("BEGIN TRANSACTION")
    try:
        connection.execute("DELETE FROM validation_issues")
        if register_path is not None and not register:
            issue(connection, register_path, "missing_people_register",
                  "No Cricinfo IDs for Cricsheet players; links fall back to exact names")
        cricsheet_count = sum(
            import_cricsheet_file(connection, path, register)
            for path in json_files(cricsheet_directories, cricsheet_match_ids)
        )
        # The same match can sit in more than one commentary folder (an India
        # v Australia T20I is in the India and the top-10 folders). Import it
        # once, from the first folder listed, and record the others.
        commentary_count, first_seen = 0, {}
        for path in commentary_files(commentary_directories):
            if path.stem in first_seen:
                issue(connection, path, "duplicate_commentary_match",
                      f"Match {path.stem} already imported from {first_seen[path.stem]}")
                continue
            first_seen[path.stem] = path.parent
            commentary_count += import_commentary_file(connection, path)
        players_count = import_players(connection, player_styles_path)
        refresh_links(connection)
        refresh_player_memory(connection)
        refresh_contextual_value_memory(connection)
        result = dict(status_rows(connection))
        connection.execute("COMMIT")
    except Exception:
        connection.execute("ROLLBACK")
        raise
    finally:
        connection.close()
    result["Imported Cricsheet deliveries this run"] = cricsheet_count
    result["Imported commentary records this run"] = commentary_count
    result["Imported player profiles this run"] = players_count
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Import existing CricketIQ data into local DuckDB.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="Generated DuckDB path")
    parser.add_argument("--cricsheet-dir", type=Path, action="append", dest="cricsheet_dirs")
    parser.add_argument("--commentary-dir", type=Path, action="append", dest="commentary_dirs")
    parser.add_argument("--player-styles", type=Path, default=DATA_DIR / "players" / "player_styles.csv")
    parser.add_argument("--people-register", type=Path, default=DATA_DIR / "cricsheet" / "people.csv",
                        help="Cricsheet's people register (maps Cricsheet player IDs to Cricinfo IDs)")
    parser.add_argument("--all", action="store_true", help="Import all local Cricsheet and commentary directories")
    args = parser.parse_args()
    defaults_cricsheet, defaults_commentary = default_paths(args.all)
    cricsheet_dirs = args.cricsheet_dirs or defaults_cricsheet
    commentary_dirs = args.commentary_dirs or defaults_commentary
    missing = [path for path in [*cricsheet_dirs, *commentary_dirs] if not path.exists()]
    if missing:
        parser.error(f"Input directories do not exist: {', '.join(str(path) for path in missing)}")
    # The default is a deliberately small, evidence-complete corpus. It is
    # enough for the first Player Intelligence workflow, while --all remains
    # available for expanding the archive later.
    matched_ids = None if args.all else {path.stem for path in commentary_files(commentary_dirs)}
    status = run_import(args.db, cricsheet_dirs, commentary_dirs, args.player_styles, matched_ids,
                        register_path=args.people_register)
    print(json.dumps(status, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
