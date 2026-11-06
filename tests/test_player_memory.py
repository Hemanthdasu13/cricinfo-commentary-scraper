from __future__ import annotations

from pathlib import Path

from cricketiq.database import connect
from cricketiq.player_memory import player_weakness_memory, refresh_player_memory


def test_memory_ranks_a_type_and_keeps_only_repeated_tactical_evidence() -> None:
    connection = connect(Path(":memory:"))
    try:
        connection.execute(
            "INSERT INTO matches VALUES ('m1', '2025-01-01', 'Indian Premier League', '2025', 'T20', "
            "'male', 'club', '[\"A\", \"B\"]', '', '', 'fixture')"
        )
        connection.executemany(
            "INSERT INTO match_players VALUES (?, ?, ?, ?)",
            [("m1", "Abhishek Sharma", "bat", "1070183"), ("m1", "Left spinner", "spin", "20"),
             ("m1", "Fast bowler", "pace", "30")],
        )
        connection.executemany(
            "INSERT INTO players VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [("spin", "Left spinner", "20", "Left spinner", 1, "B", "", "left", "spin", "left-arm orthodox", "", "", "ok"),
             ("pace", "Fast bowler", "30", "Fast bowler", 1, "B", "", "right", "pace", "fast", "", "", "ok")],
        )
        deliveries = []
        for index in range(1, 61):
            wicket = '{"player_out": "Abhishek Sharma", "kind": "caught"}' if index <= 6 else ''
            deliveries.append(("m1", 1, index, f"{index}.1", index, "Abhishek Sharma", "Left spinner", "Other", 1, 0, 1, '', wicket, "fixture"))
        for index in range(61, 161):
            wicket = '{"player_out": "Abhishek Sharma", "kind": "caught"}' if index <= 62 else ''
            deliveries.append(("m1", 1, index, f"{index}.1", index, "Abhishek Sharma", "Fast bowler", "Other", 2, 0, 2, '', wicket, "fixture"))
        connection.executemany("INSERT INTO deliveries VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", deliveries)
        commentary = []
        for row_number in range(1, 4):
            commentary.append((
                "commentary.csv", row_number, "m1", 1, f"{row_number}.1", row_number, 1, "A", "Abhishek Sharma",
                "1070183", "Left spinner", "20", "Other", 1, True, "caught", "", row_number, 1, None,
                "out", "Full outside off, tries to loft and is caught", "", "", 1, row_number,
            ))
        connection.executemany("INSERT INTO commentary_records VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", commentary)
        refresh_player_memory(connection)
        answer = player_weakness_memory(connection, "Abhishek Sharma")
        assert answer["ranked_profiles"][0]["bowling_type"] == "Left-arm orthodox"
        assert answer["primary_vulnerability"]["bowling_type"] == "Left-arm orthodox"
        assert answer["ranked_profiles"][0]["evidence_level"] == "moderate"
        assert {signal["value"] for signal in answer["top_tactical_signals"]} >= {"full", "outside off", "loft or slog"}
    finally:
        connection.close()
