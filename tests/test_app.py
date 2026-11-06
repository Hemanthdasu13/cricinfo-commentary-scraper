from pathlib import Path

from streamlit.testing.v1 import AppTest


def test_situation_lab_renders_without_computing_a_plan_recommendation() -> None:
    app = AppTest.from_file(Path(__file__).parents[1] / "app.py", default_timeout=10).run()
    assert not app.exception
    assert any("Who has the edge?" in title.value for title in app.title)
    assert any("probability estimate" in caption.value for caption in app.caption)


def test_evidence_view_states_that_the_product_is_not_for_betting() -> None:
    app = AppTest.from_file(Path(__file__).parents[1] / "app.py", default_timeout=10).run()
    app.radio[0].set_value("The evidence").run()
    assert not app.exception
    assert any("not a betting product" in warning.value for warning in app.warning)
