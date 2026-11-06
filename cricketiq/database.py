"""DuckDB schema and read models for CricketIQ's local analytical store."""

from __future__ import annotations

from pathlib import Path

import duckdb


SCHEMA = """
CREATE TABLE IF NOT EXISTS matches (
    match_id VARCHAR PRIMARY KEY,
    match_date DATE,
    competition VARCHAR,
    season VARCHAR,
    format VARCHAR,
    gender VARCHAR,
    team_type VARCHAR,
    teams_json VARCHAR NOT NULL,
    venue VARCHAR,
    outcome_json VARCHAR,
    source_path VARCHAR NOT NULL
);

CREATE TABLE IF NOT EXISTS innings (
    match_id VARCHAR NOT NULL,
    innings_number INTEGER NOT NULL,
    batting_team VARCHAR NOT NULL,
    total_runs INTEGER NOT NULL,
    wickets INTEGER NOT NULL,
    source_path VARCHAR NOT NULL,
    PRIMARY KEY (match_id, innings_number)
);

CREATE TABLE IF NOT EXISTS deliveries (
    match_id VARCHAR NOT NULL,
    innings_number INTEGER NOT NULL,
    delivery_index INTEGER NOT NULL,
    actual_delivery VARCHAR,
    over_number INTEGER NOT NULL,
    batter VARCHAR NOT NULL,
    bowler VARCHAR NOT NULL,
    non_striker VARCHAR NOT NULL,
    batter_runs INTEGER NOT NULL,
    extras_runs INTEGER NOT NULL,
    total_runs INTEGER NOT NULL,
    extras_json VARCHAR,
    wickets_json VARCHAR,
    source_path VARCHAR NOT NULL,
    PRIMARY KEY (match_id, innings_number, delivery_index)
);

-- Each Cricsheet match lists its players' Cricsheet IDs; the people register
-- maps those to Cricinfo IDs, which the commentary uses. Names differ between
-- the sources ("JA Duffy" v "Jacob Duffy"), IDs do not.
CREATE TABLE IF NOT EXISTS match_players (
    match_id VARCHAR NOT NULL,
    player_name VARCHAR NOT NULL,
    cricsheet_id VARCHAR,
    cricinfo_id VARCHAR,
    PRIMARY KEY (match_id, player_name)
);

CREATE TABLE IF NOT EXISTS commentary_matches (
    source_file VARCHAR PRIMARY KEY,
    match_id VARCHAR NOT NULL,
    series_id VARCHAR,
    match_label VARCHAR,
    format VARCHAR,
    match_class VARCHAR,
    ball_limit INTEGER,
    source_path VARCHAR NOT NULL
);

CREATE TABLE IF NOT EXISTS commentary_records (
    source_file VARCHAR NOT NULL,
    row_number INTEGER NOT NULL,
    match_id VARCHAR NOT NULL,
    innings_number INTEGER,
    over_text VARCHAR,
    over_number INTEGER,
    ball_in_over INTEGER,
    batting_team VARCHAR,
    batter VARCHAR,
    batter_id VARCHAR,
    bowler VARCHAR,
    bowler_id VARCHAR,
    non_striker VARCHAR,
    runs INTEGER,
    is_wicket BOOLEAN,
    dismissal_type VARCHAR,
    dismissal_text VARCHAR,
    innings_runs INTEGER,
    innings_wickets INTEGER,
    target INTEGER,
    short_text VARCHAR,
    commentary_text VARCHAR,
    pre_text VARCHAR,
    post_text VARCHAR,
    timestamp_ms BIGINT,
    sequence BIGINT,
    PRIMARY KEY (source_file, row_number)
);

CREATE TABLE IF NOT EXISTS commentary_links (
    source_file VARCHAR NOT NULL,
    row_number INTEGER NOT NULL,
    match_id VARCHAR NOT NULL,
    innings_number INTEGER,
    delivery_index INTEGER,
    link_status VARCHAR NOT NULL,
    candidate_count INTEGER NOT NULL,
    evidence VARCHAR NOT NULL,
    PRIMARY KEY (source_file, row_number)
);

CREATE TABLE IF NOT EXISTS players (
    cricsheet_id VARCHAR PRIMARY KEY,
    cricsheet_name VARCHAR,
    cricinfo_id VARCHAR,
    espn_name VARCHAR,
    matches INTEGER,
    teams VARCHAR,
    bat_hand VARCHAR,
    bowl_arm VARCHAR,
    bowl_kind VARCHAR,
    bowl_type VARCHAR,
    bat_style_raw VARCHAR,
    bowl_style_raw VARCHAR,
    status VARCHAR
);

CREATE TABLE IF NOT EXISTS validation_issues (
    source_path VARCHAR NOT NULL,
    issue_type VARCHAR NOT NULL,
    detail VARCHAR NOT NULL,
    recorded_at TIMESTAMP NOT NULL DEFAULT current_timestamp
);

-- Computed memory tables. They are refreshed after import so a Player
-- Intelligence query reads prepared evidence instead of rescanning raw files.
CREATE TABLE IF NOT EXISTS player_baselines (
    batter_name VARCHAR NOT NULL,
    batter_id VARCHAR,
    match_format VARCHAR NOT NULL,
    competition VARCHAR NOT NULL,
    non_wide_events INTEGER NOT NULL,
    batter_runs INTEGER NOT NULL,
    bowler_dismissals INTEGER NOT NULL,
    strike_rate DOUBLE NOT NULL,
    dismissal_rate DOUBLE NOT NULL,
    PRIMARY KEY (batter_name, match_format, competition)
);

CREATE TABLE IF NOT EXISTS player_bowling_type_memory (
    batter_name VARCHAR NOT NULL,
    batter_id VARCHAR,
    match_format VARCHAR NOT NULL,
    competition VARCHAR NOT NULL,
    bowling_type VARCHAR NOT NULL,
    bowl_arm VARCHAR,
    bowl_kind VARCHAR,
    bowl_type VARCHAR,
    non_wide_events INTEGER NOT NULL,
    batter_runs INTEGER NOT NULL,
    bowler_dismissals INTEGER NOT NULL,
    dot_events INTEGER NOT NULL,
    raw_strike_rate DOUBLE NOT NULL,
    raw_dismissal_rate DOUBLE NOT NULL,
    smoothed_strike_rate DOUBLE NOT NULL,
    smoothed_dismissal_rate DOUBLE NOT NULL,
    baseline_strike_rate DOUBLE NOT NULL,
    baseline_dismissal_rate DOUBLE NOT NULL,
    vulnerability_score DOUBLE NOT NULL,
    evidence_level VARCHAR NOT NULL,
    is_eligible BOOLEAN NOT NULL,
    PRIMARY KEY (batter_name, match_format, competition, bowling_type)
);

CREATE TABLE IF NOT EXISTS commentary_tags (
    source_file VARCHAR NOT NULL,
    row_number INTEGER NOT NULL,
    tag_category VARCHAR NOT NULL,
    tag_value VARCHAR NOT NULL,
    source_phrase VARCHAR NOT NULL,
    PRIMARY KEY (source_file, row_number, tag_category)
);

CREATE TABLE IF NOT EXISTS player_dismissal_evidence (
    batter_name VARCHAR NOT NULL,
    batter_id VARCHAR,
    match_format VARCHAR NOT NULL,
    competition VARCHAR NOT NULL,
    bowling_type VARCHAR NOT NULL,
    source_file VARCHAR NOT NULL,
    row_number INTEGER NOT NULL,
    match_id VARCHAR NOT NULL,
    innings_number INTEGER,
    over_text VARCHAR,
    bowler VARCHAR,
    dismissal_type VARCHAR,
    commentary_text VARCHAR NOT NULL,
    length_tag VARCHAR,
    line_tag VARCHAR,
    variation_tag VARCHAR,
    shot_tag VARCHAR,
    PRIMARY KEY (source_file, row_number)
);

CREATE TABLE IF NOT EXISTS player_tactical_signals (
    batter_name VARCHAR NOT NULL,
    batter_id VARCHAR,
    match_format VARCHAR NOT NULL,
    competition VARCHAR NOT NULL,
    bowling_type VARCHAR NOT NULL,
    tag_category VARCHAR NOT NULL,
    tag_value VARCHAR NOT NULL,
    dismissal_count INTEGER NOT NULL,
    tagged_dismissal_count INTEGER NOT NULL,
    dismissal_share DOUBLE NOT NULL,
    PRIMARY KEY (batter_name, match_format, competition, bowling_type, tag_category, tag_value)
);

CREATE TABLE IF NOT EXISTS player_tactical_performance (
    batter_name VARCHAR NOT NULL,
    batter_id VARCHAR,
    match_format VARCHAR NOT NULL,
    competition VARCHAR NOT NULL,
    bowling_type VARCHAR NOT NULL,
    tag_category VARCHAR NOT NULL,
    tag_value VARCHAR NOT NULL,
    non_wide_events INTEGER NOT NULL,
    batter_runs INTEGER NOT NULL,
    dot_events INTEGER NOT NULL,
    single_events INTEGER NOT NULL,
    boundary_events INTEGER NOT NULL,
    strike_rate DOUBLE NOT NULL,
    PRIMARY KEY (batter_name, match_format, competition, bowling_type, tag_category, tag_value)
);

-- Context-adjusted player value.  ``expected_batter_runs`` is generated from
-- other batters who faced the same coarse match state, never from the player
-- being scored.  This keeps a player's own historical output from defining
-- their benchmark.
CREATE TABLE IF NOT EXISTS player_context_value_memory (
    batter_name VARCHAR NOT NULL,
    batter_id VARCHAR,
    match_format VARCHAR NOT NULL,
    competition VARCHAR NOT NULL,
    non_wide_events INTEGER NOT NULL,
    batter_runs INTEGER NOT NULL,
    expected_batter_runs DOUBLE NOT NULL,
    runs_above_expected DOUBLE NOT NULL,
    runs_above_expected_per_100 DOUBLE NOT NULL,
    comparator_events INTEGER NOT NULL,
    evidence_level VARCHAR NOT NULL,
    PRIMARY KEY (batter_name, match_format, competition)
);

-- A relative type matchup: actual batter runs less the score expected of an
-- average *other* batter facing the same bowling type and match situation.
-- It deliberately does not try to forecast named batter-v-bowler pairs.
CREATE TABLE IF NOT EXISTS player_context_matchup_memory (
    batter_name VARCHAR NOT NULL,
    batter_id VARCHAR,
    match_format VARCHAR NOT NULL,
    competition VARCHAR NOT NULL,
    phase VARCHAR NOT NULL,
    bowling_type VARCHAR NOT NULL,
    non_wide_events INTEGER NOT NULL,
    batter_runs INTEGER NOT NULL,
    expected_batter_runs DOUBLE NOT NULL,
    runs_above_expected DOUBLE NOT NULL,
    runs_above_expected_per_100 DOUBLE NOT NULL,
    comparator_events INTEGER NOT NULL,
    evidence_level VARCHAR NOT NULL,
    PRIMARY KEY (batter_name, match_format, competition, phase, bowling_type)
);

-- Commentary-backed delivery-pattern read model.  A pattern exists only when
-- a commentary record links uniquely to a source delivery; untagged balls are
-- never silently classified as any line, length, or variation.
CREATE TABLE IF NOT EXISTS player_delivery_pattern_memory (
    batter_name VARCHAR NOT NULL,
    batter_id VARCHAR,
    match_format VARCHAR NOT NULL,
    competition VARCHAR NOT NULL,
    phase VARCHAR NOT NULL,
    bowling_type VARCHAR NOT NULL,
    tag_category VARCHAR NOT NULL,
    tag_value VARCHAR NOT NULL,
    tagged_events INTEGER NOT NULL,
    available_events INTEGER NOT NULL,
    commentary_linked_events INTEGER NOT NULL,
    commentary_link_coverage_pct DOUBLE NOT NULL,
    tag_share_pct DOUBLE NOT NULL,
    batter_runs INTEGER NOT NULL,
    expected_batter_runs DOUBLE NOT NULL,
    runs_above_expected DOUBLE NOT NULL,
    runs_above_expected_per_100 DOUBLE NOT NULL,
    comparator_events INTEGER NOT NULL,
    evidence_level VARCHAR NOT NULL,
    PRIMARY KEY (batter_name, match_format, competition, phase, bowling_type, tag_category, tag_value)
);

CREATE INDEX IF NOT EXISTS idx_deliveries_match_ball
    ON deliveries(match_id, innings_number, actual_delivery);
CREATE INDEX IF NOT EXISTS idx_commentary_match_ball
    ON commentary_records(match_id, innings_number, over_text);
CREATE INDEX IF NOT EXISTS idx_memory_player
    ON player_bowling_type_memory(batter_name, match_format, competition);
CREATE INDEX IF NOT EXISTS idx_evidence_player
    ON player_dismissal_evidence(batter_name, match_format, competition, bowling_type);
CREATE INDEX IF NOT EXISTS idx_tactical_performance_player
    ON player_tactical_performance(batter_name, match_format, competition, bowling_type);
CREATE INDEX IF NOT EXISTS idx_context_value_player
    ON player_context_value_memory(batter_name, match_format, competition);
CREATE INDEX IF NOT EXISTS idx_context_matchup_player
    ON player_context_matchup_memory(batter_name, match_format, competition, bowling_type);
CREATE INDEX IF NOT EXISTS idx_delivery_pattern_player
    ON player_delivery_pattern_memory(batter_name, match_format, competition, tag_category, tag_value);
"""


def connect(database_path: Path | str, *, read_only: bool = False) -> duckdb.DuckDBPyConnection:
    """Open a database, creating the parent directory and schema when needed."""
    path = Path(database_path)
    if not read_only:
        path.parent.mkdir(parents=True, exist_ok=True)
    connection = duckdb.connect(str(path), read_only=read_only)
    if not read_only:
        connection.execute(SCHEMA)
        # One-way compatibility for the initial prototype name.  A model may
        # back off from the most detailed state, so the stored number is the
        # comparator-pool size, not necessarily an exact-context count.
        migration_indexes = {
            "player_context_value_memory": (
                "idx_context_value_player",
                "CREATE INDEX IF NOT EXISTS idx_context_value_player "
                "ON player_context_value_memory(batter_name, match_format, competition)",
            ),
            "player_context_matchup_memory": (
                "idx_context_matchup_player",
                "CREATE INDEX IF NOT EXISTS idx_context_matchup_player "
                "ON player_context_matchup_memory(batter_name, match_format, competition, bowling_type)",
            ),
        }
        for table, (index, create_index) in migration_indexes.items():
            columns = {row[1] for row in connection.execute(f"PRAGMA table_info('{table}')").fetchall()}
            if "exact_context_events" in columns and "comparator_events" not in columns:
                connection.execute(f"DROP INDEX IF EXISTS {index}")
                connection.execute(f"ALTER TABLE {table} RENAME COLUMN exact_context_events TO comparator_events")
                connection.execute(create_index)
        pattern_columns = {row[1] for row in connection.execute(
            "PRAGMA table_info('player_delivery_pattern_memory')"
        ).fetchall()}
        if "tag_coverage_pct" in pattern_columns and "tag_share_pct" not in pattern_columns:
            connection.execute("DROP INDEX IF EXISTS idx_delivery_pattern_player")
            connection.execute(
                "ALTER TABLE player_delivery_pattern_memory RENAME COLUMN tag_coverage_pct TO tag_share_pct"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_delivery_pattern_player "
                "ON player_delivery_pattern_memory(batter_name, match_format, competition, tag_category, tag_value)"
            )
            pattern_columns.remove("tag_coverage_pct")
            pattern_columns.add("tag_share_pct")
        if "commentary_linked_events" not in pattern_columns:
            connection.execute(
                "ALTER TABLE player_delivery_pattern_memory "
                "ADD COLUMN commentary_linked_events INTEGER"
            )
        if "commentary_link_coverage_pct" not in pattern_columns:
            connection.execute(
                "ALTER TABLE player_delivery_pattern_memory "
                "ADD COLUMN commentary_link_coverage_pct DOUBLE"
            )
    return connection


def status_rows(connection: duckdb.DuckDBPyConnection) -> list[tuple[str, int]]:
    """Return the compact status metrics shown in the first application page."""
    queries = {
        "Cricsheet matches": "SELECT count(*) FROM matches",
        "Innings": "SELECT count(*) FROM innings",
        "Deliveries": "SELECT count(*) FROM deliveries",
        "Commentary files": "SELECT count(*) FROM commentary_matches",
        "Unique commentary matches": "SELECT count(DISTINCT match_id) FROM commentary_matches",
        "Commentary records": "SELECT count(*) FROM commentary_records",
        "Verified commentary links": "SELECT count(*) FROM commentary_links WHERE link_status = 'linked'",
        "Players with a Cricinfo ID": "SELECT count(DISTINCT cricsheet_id) FROM match_players WHERE cricinfo_id <> ''",
        "Player profiles": "SELECT count(*) FROM players",
        "Validation issues": "SELECT count(*) FROM validation_issues",
    }
    return [(label, int(connection.execute(query).fetchone()[0])) for label, query in queries.items()]
