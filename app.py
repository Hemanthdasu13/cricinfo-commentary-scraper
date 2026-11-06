"""Initial Streamlit interface for CricketIQ's data foundation."""

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


st.set_page_config(page_title="CricketIQ", page_icon="🏏", layout="wide")
st.markdown(
    """<style>
    .stApp { background: #07130f; color: #e6eee9; }
    [data-testid="stSidebar"] { background: #0d2119; }
    .stMetric { background: #102a20; border: 1px solid #234534; border-radius: 10px; padding: 12px; }
    </style>""",
    unsafe_allow_html=True,
)

st.sidebar.title("CricketIQ")
page = st.sidebar.radio(
    "Navigate",
    ["Data status", "Decision odds", "About the evidence"],
    label_visibility="collapsed",
)


@st.cache_data(max_entries=12, show_spinner=False)
def recent_odi_chase_states(as_of: date):
    """Load a bounded recent ODI reference set for the interactive prototype."""
    return load_odi_chase_states(
        ROOT / "data" / "cricsheet" / "odis_male",
        before=as_of,
        minimum_match_id=1_300_000,
    )

if page == "Data status":
    st.title("CricketIQ data status")
    st.caption("Facts and source commentary are imported separately; links are created only when the delivery match is unambiguous.")
    if not DEFAULT_DB_PATH.exists():
        st.warning("No local database yet. Run the IPL starter import first.")
        st.code(r".\.venv\Scripts\python.exe -m cricketiq.ingest", language="powershell")
    else:
        connection = connect(DEFAULT_DB_PATH, read_only=True)
        metrics = status_rows(connection)
        values = dict(metrics)
        columns = st.columns(3)
        for index, (label, value) in enumerate(metrics):
            columns[index % 3].metric(label, f"{value:,}")
        st.subheader("Coverage and link confidence")
        st.write(
            f"{values['Verified commentary links']:,} of {values['Commentary records']:,} commentary records link to a "
            "Cricsheet delivery using six checks: match, innings, ball label, batter and bowler (by Cricinfo ID), "
            "and runs. All other records remain unresolved rather than guessed."
        )
        recent_issues = connection.execute(
            "SELECT issue_type, detail, source_path FROM validation_issues ORDER BY recorded_at DESC LIMIT 25"
        ).fetchdf()
        if values["Validation issues"]:
            st.subheader("Validation issues")
            st.dataframe(recent_issues, use_container_width=True, hide_index=True)
        else:
            st.success("No validation issues were recorded during the latest import.")
        connection.close()
elif page == "Decision odds":
    st.title("Decision odds")
    st.caption("A time-locked baseline for ODI chases. It estimates the match state, not whether a named bowling change was right.")
    st.info(
        "This beta view deliberately blocks player-level captaincy recommendations. "
        "Those require a separate counterfactual model that has passed held-out validation.",
        title="Evidence guardrail",
    )
    with st.form("decision_state"):
        left, middle, right = st.columns(3)
        with left:
            target = st.number_input("Target", min_value=2, max_value=600, value=326, step=1)
            score = st.number_input("Current score", min_value=0, max_value=599, value=230, step=1)
        with middle:
            wickets = st.number_input("Wickets lost", min_value=0, max_value=9, value=5, step=1)
            balls_remaining = st.number_input("Legal balls remaining", min_value=1, max_value=300, value=79, step=1)
        with right:
            as_of = st.date_input("Information available through", value=date(2026, 10, 31))
        submitted = st.form_submit_button("Estimate state odds", width="stretch")

    if submitted:
        if score >= target:
            st.success("The target has already been reached.")
        else:
            result_slot = st.container()
            with result_slot:
                with st.spinner("Building a time-prior ODI comparison set..."):
                    history = recent_odi_chase_states(as_of)
                    query = ChaseState("interactive", as_of, int(target), int(score), int(wickets), int(balls_remaining), False)
                    estimate = CalibratedStateOdds(history).estimate(query)
            chasing = estimate.chase_win_probability
            with st.container(horizontal=True):
                st.metric("Chasing side", f"{chasing:.1%}", border=True)
                st.metric("Defending side", f"{1 - chasing:.1%}", border=True)
                st.metric("80% uncertainty band", f"{estimate.lower_80:.1%}–{estimate.upper_80:.1%}", border=True)
                st.metric("Effective comparisons", f"{estimate.effective_sample_size:.0f}", border=True)
            st.caption(
                "This estimate uses historical states dated before the selected cutoff, matched on target, required rate, "
                "balls remaining and wickets. It is a baseline control, not a betting price or a bowling-plan recommendation."
            )
else:
    st.title("Evidence-first by design")
    st.markdown(
        """
        CricketIQ is being built around a simple rule: **the database retrieves, Python calculates, and AI explains**.

        This first screen is intentionally limited to import coverage. It does not make tactical claims, generate an
        analysis, or infer delivery context. Those features will be added only after their source data and calculations
        are present and testable.
        """
    )
