from pathlib import Path

from streamlit.testing.v1 import AppTest


def test_decision_odds_view_renders_without_computing_a_plan_recommendation() -> None:
    app = AppTest.from_file(Path(__file__).parents[1] / "app.py", default_timeout=10).run()
    app.radio[0].set_value("Decision odds").run()
    assert not app.exception
    assert any("Decision odds" in title.value for title in app.title)
    assert any("captaincy recommendations" in info.value for info in app.info)
