from __future__ import annotations

from pathlib import Path

from cricketiq.ingest import run_import


FIXTURES = Path(__file__).parent / "fixtures"


def test_imports_and_links_an_unambiguous_delivery() -> None:
    status = run_import(
        Path(":memory:"),
        [FIXTURES / "cricsheet"],
        [FIXTURES / "commentary"],
        FIXTURES / "none.csv",
    )
    assert status["Cricsheet matches"] == 1
    assert status["Deliveries"] == 1
    assert status["Commentary records"] == 1
    assert status["Verified commentary links"] == 1


def test_links_by_cricinfo_id_when_names_differ() -> None:
    # Cricsheet says "JA Duffy" and "B Sai Sudharsan"; the commentary says
    # "Jacob Duffy" and "Sai Sudharsan". The people register joins them by ID.
    # The wide is labelled 0.1 in the commentary and 0.2 in Cricsheet.
    ids = FIXTURES / "ids"
    status = run_import(
        Path(":memory:"),
        [ids / "cricsheet"],
        [ids / "commentary"],
        FIXTURES / "none.csv",
        register_path=ids / "people.csv",
    )
    assert status["Deliveries"] == 3
    assert status["Commentary records"] == 3
    assert status["Verified commentary links"] == 3
    assert status["Players with a Cricinfo ID"] == 3


def test_names_that_differ_do_not_link_without_the_register() -> None:
    ids = FIXTURES / "ids"
    status = run_import(
        Path(":memory:"),
        [ids / "cricsheet"],
        [ids / "commentary"],
        FIXTURES / "none.csv",
    )
    assert status["Verified commentary links"] == 0


def test_two_records_claiming_one_delivery_are_both_left_unresolved(tmp_path: Path) -> None:
    commentary = tmp_path / "commentary"
    commentary.mkdir()
    source = (FIXTURES / "commentary" / "9001.csv").read_text(encoding="utf-8").splitlines()
    # The same ball twice, with a different sequence number.
    (commentary / "9001.csv").write_text("\n".join([*source, source[1].rsplit(",", 1)[0] + ",2"]) + "\n",
                                         encoding="utf-8")
    status = run_import(Path(":memory:"), [FIXTURES / "cricsheet"], [commentary], FIXTURES / "none.csv")
    assert status["Commentary records"] == 2
    assert status["Verified commentary links"] == 0


def test_a_match_in_two_commentary_folders_is_imported_once() -> None:
    status = run_import(
        Path(":memory:"),
        [FIXTURES / "cricsheet"],
        [FIXTURES / "commentary", FIXTURES / "commentary"],
        FIXTURES / "none.csv",
    )
    assert status["Commentary records"] == 1
    assert status["Validation issues"] == 1
