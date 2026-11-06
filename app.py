"""The first public-facing CricBuddy experience: ODI chase situation analysis."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cricketiq.config import DEFAULT_DB_PATH
from cricketiq.database import connect, status_rows
from cricketiq.decision_model import CalibratedStateOdds, ChaseState, load_odi_chase_states


REFERENCE_DATA_END = date(2026, 10, 31)
ODI_DIRECTORY = ROOT / "data" / "cricsheet" / "odis_male"


st.set_page_config(
    page_title="CricBuddy | Situation lab",
    page_icon=":material/sports_cricket:",
    layout="wide",
)


@st.cache_data(max_entries=2, show_spinner=False)
def recent_odi_chase_states(as_of: date):
    """Load reproducible, time-locked ODI chase snapshots for the calculator."""
    return load_odi_chase_states(
        ODI_DIRECTORY,
        before=as_of,
        minimum_match_id=1_300_000,
    )


def sidebar() -> str:
    with st.sidebar:
        st.title("CricBuddy", icon=":material/sports_cricket:")
        st.caption("A smarter way to watch cricket.")
        page = st.radio(
            "Navigate",
            ["Situation lab", "How it works", "The evidence"],
            label_visibility="collapsed",
        )
        st.space("medium")
        st.badge("Prototype", icon=":material/science:", color="blue")
        st.caption("For fans, not betting. Every estimate shows its uncertainty.")
    return page


def situation_lab() -> None:
    st.title("Who has the edge?")
    st.markdown(
        "Enter an ODI chase situation to see an evidence-backed estimate from comparable historical match states."
    )
    st.caption(
        f"Reference data is locked through {REFERENCE_DATA_END.day} {REFERENCE_DATA_END:%B %Y}. This is a probability estimate, not a prediction or betting price."
    )

    with st.container(border=True):
        st.subheader("Describe the chase", icon=":material/tune:")
        with st.form("chase_state"):
            first, second, third = st.columns(3)
            with first:
                target = st.number_input("Target", min_value=2, max_value=600, value=326, step=1)
                score = st.number_input("Current score", min_value=0, max_value=599, value=230, step=1)
            with second:
                wickets = st.number_input("Wickets lost", min_value=0, max_value=9, value=5, step=1)
                balls_remaining = st.number_input(
                    "Legal balls remaining", min_value=1, max_value=300, value=79, step=1
                )
            with third:
                st.markdown("**What this uses**")
                st.caption("Target, required rate, wickets and balls remaining. Player and venue effects are not yet included.")
                st.caption(f"Dataset cutoff: {REFERENCE_DATA_END:%d %b %Y}")
            submitted = st.form_submit_button(
                "Estimate the chase", type="primary", icon=":material/query_stats:", width="stretch"
            )

    result_area = st.container()
    if not submitted:
        with result_area.container(border=True):
            st.subheader("Start with a real match state", icon=":material/play_circle:")
            st.markdown(
                "Use the fields above to test any ODI chase. CricBuddy will show the probability, its uncertainty, and the amount of historical support behind it."
            )
        return

    if score >= target:
        st.success("The target has already been reached.", icon=":material/check_circle:")
        return

    if score > target - 1:
        st.error("Current score must be below the target.", icon=":material/error:")
        return

    with result_area.skeleton(height=300):
        history = recent_odi_chase_states(REFERENCE_DATA_END)
        if len(history) < 50:
            st.error(
                "The historical ODI reference set is not available in this deployment yet.",
                icon=":material/database_off:",
            )
            return
        query = ChaseState(
            "interactive",
            REFERENCE_DATA_END,
            int(target),
            int(score),
            int(wickets),
            int(balls_remaining),
            False,
        )
        estimate = CalibratedStateOdds(history).estimate(query)

    runs_required = query.runs_required
    required_rate = query.required_rate
    st.header("The situation", icon=":material/insights:")
    primary, support, uncertainty, rate = st.columns(4)
    primary.metric("Chasing side win chance", f"{estimate.chase_win_probability:.0%}", border=True)
    support.metric("Comparable historical support", f"{estimate.effective_sample_size:.0f}", border=True)
    uncertainty.metric("80% uncertainty band", f"{estimate.lower_80:.0%}–{estimate.upper_80:.0%}", border=True)
    rate.metric("Required rate", f"{required_rate:.2f}", f"{runs_required} runs needed", border=True)

    with st.container(border=True):
        st.subheader("What this means", icon=":material/lightbulb:")
        st.markdown(
            f"At **{score}/{wickets}**, the chasing side needs **{runs_required} from {balls_remaining} legal balls**. "
            f"CricBuddy found a weighted set of historical ODI chase states with similar targets, required rates, "
            f"wickets and time remaining. Those states produce a central estimate of **{estimate.chase_win_probability:.0%}**."
        )
        st.caption(
            "The range is deliberately shown because no match state is certain. More comparable history produces a more stable estimate."
        )

    with st.expander("How the estimate is calculated", icon=":material/biotech:"):
        st.markdown(
            "CricBuddy compares the entered state with historical ODI chases known before the data cutoff. "
            "The closest 250 states are weighted by similarity in required rate, balls remaining, wickets lost and target. "
            "A conservative prior keeps a narrow slice of history from producing a misleading 0% or 100% result."
        )
        st.caption(
            "This is a match-state baseline only. It does not yet judge a captaincy decision or account for named players, bowling plans, venue or weather."
        )


def how_it_works() -> None:
    st.title("A cricket companion, not a tip sheet")
    st.markdown(
        "CricBuddy gives fans context before the next important moment—not a false promise about what will happen."
    )
    first, second, third = st.columns(3)
    with first.container(border=True, height="stretch"):
        st.subheader("1. Start with evidence", icon=":material/database:")
        st.markdown("Historical ball-by-ball data is structured and checked before it reaches the analysis layer.")
    with second.container(border=True, height="stretch"):
        st.subheader("2. Compare the situation", icon=":material/compare_arrows:")
        st.markdown("The prototype finds comparable ODI chases rather than pretending every match is the same.")
    with third.container(border=True, height="stretch"):
        st.subheader("3. Explain the uncertainty", icon=":material/fact_check:")
        st.markdown("Every insight carries its sample support and range. Thin evidence stays visibly thin.")

    st.header("What comes next", icon=":material/rocket_launch:")
    st.markdown(
        "The next product increments will add player matchups, phase-specific patterns and live-match prompts—only after each feature can be calculated and validated from the data."
    )


def evidence() -> None:
    st.title("The evidence behind CricBuddy")
    st.markdown("The product rule is simple: **data retrieves, Python calculates, and AI explains.**")

    with st.container(border=True):
        st.subheader("Current launch feature", icon=":material/check_circle:")
        st.markdown(
            "The situation lab uses time-locked ODI chase snapshots from Cricsheet match records. It estimates the state of a chase; it does not make player-level or captaincy recommendations."
        )
        st.caption("Cricsheet data is available under the Open Data Commons Attribution License (ODC-BY).")

    with st.expander("Local data foundation", icon=":material/storage:"):
        if not DEFAULT_DB_PATH.exists():
            st.info(
                "The local analysis database has not been imported in this environment. The situation lab uses the separate ODI reference files.",
                icon=":material/info:",
            )
            return
        try:
            connection = connect(DEFAULT_DB_PATH, read_only=True)
            metrics = status_rows(connection)
            connection.close()
        except Exception:
            st.info(
                "The local analysis database is busy while new data is being processed. The launch feature remains available because it uses the separate ODI reference files.",
                icon=":material/hourglass_top:",
            )
        else:
            for column, (label, value) in zip(st.columns(3), metrics):
                column.metric(label, f"{value:,}", border=True)

    st.warning(
        "CricBuddy is for understanding cricket. It is not a betting product and should not be used to make wagering decisions.",
        icon=":material/gpp_maybe:",
    )


page = sidebar()
if page == "Situation lab":
    situation_lab()
elif page == "How it works":
    how_it_works()
else:
    evidence()
