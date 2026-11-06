"""Precomputed, evidence-bounded memory for Player Intelligence questions.

Cricsheet supplies every performance number. Commentary is only used to retain
verbatim tactical context behind dismissals, never to create statistics.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb

from cricketiq.config import DEFAULT_DB_PATH
from cricketiq.database import connect


PRIOR_EVENTS = 60
MINIMUM_EVENTS = 50
MINIMUM_DISMISSALS = 3


@dataclass(frozen=True)
class CommentaryTag:
    category: str
    value: str
    phrase: str


TAG_RULES: dict[str, tuple[tuple[str, re.Pattern[str]], ...]] = {
    "length": (
        ("yorker", re.compile(r"\b(?:yorker|toe-crusher)\b", re.I)),
        ("full", re.compile(r"\b(?:full(?:er|ish)?|overpitched|half-volley)\b", re.I)),
        ("short", re.compile(r"\b(?:short(?:er)?|bouncer|banged in)\b", re.I)),
        ("back of a length", re.compile(r"\b(?:back of a length|hard length|on a length)\b", re.I)),
    ),
    "line": (
        ("outside off", re.compile(r"\b(?:outside off|sixth stump|wide outside off)\b", re.I)),
        ("off stump", re.compile(r"\b(?:on off|off stump|middle and off)\b", re.I)),
        ("middle or leg", re.compile(r"\b(?:middle and leg|on leg|down leg|pads|leg stump)\b", re.I)),
    ),
    "variation": (
        ("slower ball", re.compile(r"\b(?:slower ball|off-pace|change in pace|slows? it down)\b", re.I)),
        ("cutter", re.compile(r"\b(?:cutter|knuckle ball)\b", re.I)),
        ("googly", re.compile(r"\bgoogly\b", re.I)),
        ("turn or drift", re.compile(r"\b(?:turning|spinning|drift)\b", re.I)),
    ),
    "shot": (
        ("loft or slog", re.compile(r"\b(?:loft|slog|hoick|heav(?:e|ing)|go(?:es)? over)\b", re.I)),
        ("sweep", re.compile(r"\b(?:sweep|reverse sweep)\b", re.I)),
        ("pull or hook", re.compile(r"\b(?:pull|hook)\b", re.I)),
        ("drive", re.compile(r"\b(?:drive|driving)\b", re.I)),
    ),
}


def extract_commentary_tags(text: str) -> list[CommentaryTag]:
    """Extract one source phrase per tag category, so every tag is auditable."""
    found: list[CommentaryTag] = []
    for category, rules in TAG_RULES.items():
        for value, pattern in rules:
            match = pattern.search(text or "")
            if match:
                found.append(CommentaryTag(category, value, match.group(0)))
                break
    return found


def bowling_type_label(arm: str, kind: str, bowl_type: str) -> str:
    if not kind or not bowl_type:
        return "Unknown bowling type"
    if bowl_type.startswith("left-arm"):
        return bowl_type.replace("left-arm", "Left-arm", 1)
    if kind == "pace":
        return f"{arm.title()}-arm {bowl_type}"
    if bowl_type in {"off-break", "leg-break"}:
        return f"{arm.title()}-arm {bowl_type}"
    if bowl_type == "wrist spin":
        return f"{arm.title()}-arm wrist spin"
    return f"{arm.title()}-arm {bowl_type}"


def refresh_commentary_tags(connection: duckdb.DuckDBPyConnection) -> None:
    connection.execute("DELETE FROM commentary_tags")
    rows = [
        [source_file, row_number, tag.category, tag.value, tag.phrase]
        for source_file, row_number, text in connection.execute(
            "SELECT source_file, row_number, commentary_text FROM commentary_records"
        ).fetchall()
        for tag in extract_commentary_tags(text)
    ]
    if rows:
        connection.executemany("INSERT INTO commentary_tags VALUES (?, ?, ?, ?, ?)", rows)


def _events(connection: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    """Return source facts enriched with player IDs and bowling-style metadata."""
    result = connection.execute(
        """
        SELECT d.batter AS batter_name, COALESCE(bat.cricinfo_id, '') AS batter_id,
               m.format AS match_format, m.competition,
               COALESCE(bowl_profile.bowl_arm, '') AS bowl_arm,
               COALESCE(bowl_profile.bowl_kind, '') AS bowl_kind,
               COALESCE(bowl_profile.bowl_type, '') AS bowl_type,
               CASE WHEN d.extras_json LIKE '%"wides"%' THEN 0 ELSE 1 END AS non_wide_event,
               d.batter_runs,
               CASE WHEN d.extras_json NOT LIKE '%"wides"%' AND d.batter_runs = 0 THEN 1 ELSE 0 END AS dot_event,
               CASE WHEN strpos(d.wickets_json, '"player_out": "' || d.batter || '"') > 0
                          AND d.wickets_json NOT LIKE '%"kind": "run out"%'
                          AND d.wickets_json NOT LIKE '%"kind": "retired hurt"%'
                          AND d.wickets_json NOT LIKE '%"kind": "obstructing the field"%'
                    THEN 1 ELSE 0 END AS bowler_dismissal
        FROM deliveries d
        JOIN matches m ON m.match_id = d.match_id
        LEFT JOIN match_players bat ON bat.match_id = d.match_id AND bat.player_name = d.batter
        LEFT JOIN match_players bowl ON bowl.match_id = d.match_id AND bowl.player_name = d.bowler
        LEFT JOIN players bowl_profile ON bowl_profile.cricsheet_id = bowl.cricsheet_id
        """
    )
    columns = [column[0] for column in result.description]
    return [dict(zip(columns, row)) for row in result.fetchall()]


def refresh_player_memory(connection: duckdb.DuckDBPyConnection) -> None:
    """Build the fast query layer after raw data has been imported."""
    refresh_commentary_tags(connection)
    for table in (
        "player_baselines", "player_bowling_type_memory", "player_dismissal_evidence", "player_tactical_signals",
        "player_tactical_performance",
    ):
        connection.execute(f"DELETE FROM {table}")

    baselines: dict[tuple[str, str, str], dict[str, Any]] = defaultdict(
        lambda: {"events": 0, "runs": 0, "dismissals": 0, "batter_id": ""}
    )
    profiles: dict[tuple[str, str, str, str, str, str, str], dict[str, Any]] = defaultdict(
        lambda: {"events": 0, "runs": 0, "dismissals": 0, "dots": 0, "batter_id": ""}
    )
    for event in _events(connection):
        if not event["non_wide_event"]:
            continue
        base_key = (event["batter_name"], event["match_format"], event["competition"])
        baseline = baselines[base_key]
        baseline["events"] += 1
        baseline["runs"] += event["batter_runs"]
        baseline["dismissals"] += event["bowler_dismissal"]
        baseline["batter_id"] = event["batter_id"]
        label = bowling_type_label(event["bowl_arm"], event["bowl_kind"], event["bowl_type"])
        profile_key = (*base_key, label, event["bowl_arm"], event["bowl_kind"], event["bowl_type"])
        profile = profiles[profile_key]
        profile["events"] += 1
        profile["runs"] += event["batter_runs"]
        profile["dismissals"] += event["bowler_dismissal"]
        profile["dots"] += event["dot_event"]
        profile["batter_id"] = event["batter_id"]

    baseline_rows = []
    for (name, match_format, competition), values in baselines.items():
        events = values["events"]
        baseline_rows.append([
            name, values["batter_id"], match_format, competition, events, values["runs"], values["dismissals"],
            100 * values["runs"] / events, 100 * values["dismissals"] / events,
        ])
    if baseline_rows:
        connection.executemany("INSERT INTO player_baselines VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", baseline_rows)

    memory_rows = []
    for key, values in profiles.items():
        name, match_format, competition, label, arm, kind, bowl_type = key
        baseline = baselines[(name, match_format, competition)]
        events, runs, dismissals = values["events"], values["runs"], values["dismissals"]
        baseline_rpe = baseline["runs"] / baseline["events"]
        baseline_dismissal = baseline["dismissals"] / baseline["events"]
        smoothed_rpe = (runs + PRIOR_EVENTS * baseline_rpe) / (events + PRIOR_EVENTS)
        smoothed_dismissal = (dismissals + PRIOR_EVENTS * baseline_dismissal) / (events + PRIOR_EVENTS)
        scoring_penalty = max((baseline_rpe - smoothed_rpe) / baseline_rpe, 0) if baseline_rpe else 0
        dismissal_penalty = max(smoothed_dismissal / baseline_dismissal - 1, 0) if baseline_dismissal else 0
        reliability = events / (events + PRIOR_EVENTS)
        score = 100 * reliability * (0.65 * scoring_penalty + 0.35 * dismissal_penalty)
        eligible = events >= MINIMUM_EVENTS and dismissals >= MINIMUM_DISMISSALS and label != "Unknown bowling type"
        level = "high" if events >= 150 and dismissals >= 6 else "moderate" if eligible else "limited"
        memory_rows.append([
            name, values["batter_id"], match_format, competition, label, arm, kind, bowl_type,
            events, runs, dismissals, values["dots"], 100 * runs / events, 100 * dismissals / events,
            100 * smoothed_rpe, 100 * smoothed_dismissal, 100 * baseline_rpe, 100 * baseline_dismissal,
            score, level, eligible,
        ])
    if memory_rows:
        connection.executemany(
            "INSERT INTO player_bowling_type_memory VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            memory_rows,
        )
    _refresh_dismissal_evidence(connection)
    _refresh_tactical_performance(connection)


def _refresh_dismissal_evidence(connection: duckdb.DuckDBPyConnection) -> None:
    evidence = connection.execute(
        """
        SELECT c.batter, c.batter_id, m.format, m.competition,
               COALESCE(p.bowl_arm, ''), COALESCE(p.bowl_kind, ''), COALESCE(p.bowl_type, ''),
               c.source_file, c.row_number, c.match_id, c.innings_number, c.over_text,
               c.bowler, c.dismissal_type, c.commentary_text
        FROM commentary_records c
        JOIN matches m ON m.match_id = c.match_id
        LEFT JOIN players p ON c.bowler_id = p.cricinfo_id
        WHERE c.is_wicket AND c.dismissal_type NOT IN ('run out', 'retired hurt', 'obstructing the field')
          AND c.batter <> ''
        """
    ).fetchall()
    tags: dict[tuple[str, int], dict[str, str]] = defaultdict(dict)
    for source_file, row_number, category, value in connection.execute(
        "SELECT source_file, row_number, tag_category, tag_value FROM commentary_tags"
    ).fetchall():
        tags[(source_file, row_number)][category] = value
    rows = []
    for item in evidence:
        (batter, batter_id, match_format, competition, arm, kind, bowl_type, source_file, row_number,
         match_id, innings_number, over_text, bowler, dismissal_type, text) = item
        found = tags[(source_file, row_number)]
        rows.append([
            batter, batter_id, match_format, competition, bowling_type_label(arm, kind, bowl_type),
            source_file, row_number, match_id, innings_number, over_text, bowler, dismissal_type, text,
            found.get("length", ""), found.get("line", ""), found.get("variation", ""), found.get("shot", ""),
        ])
    if rows:
        connection.executemany("INSERT INTO player_dismissal_evidence VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
    counts: Counter[tuple[str, str, str, str, str, str]] = Counter()
    totals: Counter[tuple[str, str, str, str, str]] = Counter()
    for row in rows:
        for category, value in zip(("length", "line", "variation", "shot"), row[13:17]):
            if value:
                totals[(*row[:5], category)] += 1
                counts[(*row[:5], category, value)] += 1
    signals = [
        [*key[:5], key[5], key[6], count, totals[key[:6]], count / totals[key[:6]]]
        for key, count in counts.items()
    ]
    if signals:
        connection.executemany("INSERT INTO player_tactical_signals VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", signals)


def _refresh_tactical_performance(connection: duckdb.DuckDBPyConnection) -> None:
    """Aggregate exact batter outcomes for commentary-recognised ball patterns."""
    tagged_deliveries = connection.execute(
        """
        SELECT d.batter, COALESCE(c.batter_id, bat.cricinfo_id, ''), m.format, m.competition,
               COALESCE(profile.bowl_arm, ''), COALESCE(profile.bowl_kind, ''), COALESCE(profile.bowl_type, ''),
               CASE WHEN d.extras_json LIKE '%"wides"%' THEN 0 ELSE 1 END,
               d.batter_runs,
               max(CASE WHEN t.tag_category = 'length' THEN t.tag_value END) AS length_tag,
               max(CASE WHEN t.tag_category = 'line' THEN t.tag_value END) AS line_tag,
               max(CASE WHEN t.tag_category = 'variation' THEN t.tag_value END) AS variation_tag,
               max(CASE WHEN t.tag_category = 'shot' THEN t.tag_value END) AS shot_tag
        FROM commentary_records c
        JOIN commentary_links l ON l.source_file = c.source_file AND l.row_number = c.row_number
                               AND l.link_status = 'linked'
        JOIN deliveries d ON d.match_id = l.match_id AND d.innings_number = l.innings_number
                          AND d.delivery_index = l.delivery_index
        JOIN matches m ON m.match_id = d.match_id
        LEFT JOIN match_players bat ON bat.match_id = d.match_id AND bat.player_name = d.batter
        LEFT JOIN match_players bowl ON bowl.match_id = d.match_id AND bowl.player_name = d.bowler
        LEFT JOIN players profile ON profile.cricsheet_id = bowl.cricsheet_id
        LEFT JOIN commentary_tags t ON t.source_file = c.source_file AND t.row_number = c.row_number
        GROUP BY d.batter, c.batter_id, bat.cricinfo_id, m.format, m.competition,
                 profile.bowl_arm, profile.bowl_kind, profile.bowl_type, d.extras_json, d.batter_runs,
                 d.match_id, d.innings_number, d.delivery_index
        """
    ).fetchall()
    profiles: dict[tuple[str, str, str, str, str, str, str], dict[str, int]] = defaultdict(
        lambda: {"events": 0, "runs": 0, "dots": 0, "singles": 0, "boundaries": 0}
    )
    for item in tagged_deliveries:
        batter, batter_id, match_format, competition, arm, kind, bowl_type, non_wide, runs, *tags = item
        if not non_wide:
            continue
        style = bowling_type_label(arm, kind, bowl_type)
        tag_values = list(zip(("length", "line", "variation", "shot"), tags))
        length, line = tags[0], tags[1]
        if length and line:
            tag_values.append(("length + line", f"{length}; {line}"))
        for category, value in tag_values:
            if not value:
                continue
            key = (batter, batter_id, match_format, competition, style, category, value)
            profile = profiles[key]
            profile["events"] += 1
            profile["runs"] += runs
            profile["dots"] += int(runs == 0)
            profile["singles"] += int(runs == 1)
            profile["boundaries"] += int(runs in {4, 6})
    rows = [
        [*key, values["events"], values["runs"], values["dots"], values["singles"], values["boundaries"],
         100 * values["runs"] / values["events"]]
        for key, values in profiles.items()
    ]
    if rows:
        connection.executemany("INSERT INTO player_tactical_performance VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)


def player_weakness_memory(
    connection: duckdb.DuckDBPyConnection, player_name: str, *, match_format: str = "T20",
    competition: str = "Indian Premier League", limit: int = 3,
) -> dict[str, Any]:
    """Serve the reusable 'which bowling type troubles this batter?' request."""
    result = connection.execute(
        """SELECT * FROM player_bowling_type_memory
           WHERE lower(batter_name) = lower(?) AND match_format = ? AND competition = ? AND is_eligible
           ORDER BY vulnerability_score DESC, non_wide_events DESC LIMIT ?""",
        [player_name, match_format, competition, limit],
    )
    columns = [column[0] for column in result.description]
    profiles = [dict(zip(columns, row)) for row in result.fetchall()]
    if not profiles:
        raise ValueError(f"No eligible {match_format} {competition} memory for {player_name!r}.")
    top = profiles[0]
    signals = connection.execute(
        """SELECT tag_category, tag_value, dismissal_count, tagged_dismissal_count, dismissal_share
           FROM player_tactical_signals
           WHERE lower(batter_name) = lower(?) AND match_format = ? AND competition = ? AND bowling_type = ?
             AND dismissal_count >= 2 AND dismissal_share >= 0.35
           ORDER BY dismissal_count DESC, dismissal_share DESC""",
        [player_name, match_format, competition, top["bowling_type"]],
    ).fetchall()
    evidence = connection.execute(
        """SELECT match_id, innings_number, over_text, bowler, dismissal_type, commentary_text
           FROM player_dismissal_evidence
           WHERE lower(batter_name) = lower(?) AND match_format = ? AND competition = ? AND bowling_type = ?
           ORDER BY match_id, innings_number, over_text LIMIT 3""",
        [player_name, match_format, competition, top["bowling_type"]],
    ).fetchall()
    tactical_performance = connection.execute(
        """SELECT tag_category, tag_value, non_wide_events, batter_runs, dot_events, single_events,
                  boundary_events, strike_rate
           FROM player_tactical_performance
           WHERE lower(batter_name) = lower(?) AND match_format = ? AND competition = ? AND bowling_type = ?
             AND non_wide_events >= 12 AND strike_rate < ?
           ORDER BY strike_rate ASC, non_wide_events DESC LIMIT 5""",
        [player_name, match_format, competition, top["bowling_type"], top["raw_strike_rate"] * 0.85],
    ).fetchall()
    baseline = connection.execute(
        """SELECT strike_rate, dismissal_rate, non_wide_events FROM player_baselines
           WHERE lower(batter_name) = lower(?) AND match_format = ? AND competition = ?""",
        [player_name, match_format, competition],
    ).fetchone()
    return {
        "player": player_name,
        "scope": {"format": match_format, "competition": competition},
        "baseline": {"strike_rate": baseline[0], "dismissal_rate": baseline[1], "events": baseline[2]},
        "ranked_profiles": profiles,
        "primary_vulnerability": profiles[0],
        "greatest_scoring_suppression": min(profiles, key=lambda profile: profile["smoothed_strike_rate"]),
        "highest_wicket_risk": max(profiles, key=lambda profile: profile["smoothed_dismissal_rate"]),
        "top_tactical_signals": [dict(zip(("category", "value", "dismissals", "tagged_dismissals", "share"), row)) for row in signals],
        "tactical_performance_signals": [dict(zip(
            ("category", "value", "events", "runs", "dots", "singles", "boundaries", "strike_rate"), row
        )) for row in tactical_performance],
        "evidence": [dict(zip(("match_id", "innings", "over", "bowler", "dismissal_type", "commentary"), row)) for row in evidence],
        "method": {"prior_events": PRIOR_EVENTS, "minimum_events": MINIMUM_EVENTS, "minimum_dismissals": MINIMUM_DISMISSALS},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Query CricketIQ's precomputed Player Intelligence memory.")
    parser.add_argument("player", nargs="?", help="Player name")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--refresh", action="store_true", help="Rebuild memory after a completed import")
    parser.add_argument("--format", default="T20")
    parser.add_argument("--competition", default="Indian Premier League")
    args = parser.parse_args()
    connection = connect(args.db, read_only=not args.refresh)
    try:
        if args.refresh:
            connection.execute("BEGIN TRANSACTION")
            try:
                refresh_player_memory(connection)
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise
        elif args.player:
            print(json.dumps(player_weakness_memory(
                connection, args.player, match_format=args.format, competition=args.competition,
            ), indent=2, default=str))
        else:
            parser.error("player is required unless --refresh is used")
    finally:
        connection.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
