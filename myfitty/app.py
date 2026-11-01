from datetime import date, timedelta

import altair as alt
import pandas as pd
import streamlit as st

from myfitty import db, queries
from myfitty.config import ConfigError, load_config
from myfitty.ingest.importer import scan
from myfitty.rescore import remove_threshold, save_threshold, seed_thresholds

CTL_COLOR, ATL_COLOR, TSB_COLOR = "#2a78d6", "#eb6834", "#1baf7a"  # categorical slots 1-3

st.set_page_config(page_title="myfitty", layout="wide")
alt.data_transformers.disable_max_rows()
try:
    cfg = load_config()
except ConfigError as e:
    st.error(f"Config error: {e}")
    st.stop()


# --- cached reads (cleared after any import or threshold change) -------------------------------

@st.cache_data(show_spinner=False)
def load_sports(db_path: str) -> list[str]:
    with db.connect(db_path) as con:
        return queries.sports(con)


@st.cache_data(show_spinner=False)
def load_pmc(db_path: str, sport, start, end) -> pd.DataFrame:
    with db.connect(db_path) as con:
        return queries.pmc(con, sport, start, end)


@st.cache_data(show_spinner=False)
def load_weekly(db_path: str, sport, start, end) -> pd.DataFrame:
    with db.connect(db_path) as con:
        return queries.weekly(con, sport, start, end)


@st.cache_data(show_spinner=False)
def load_activities(db_path: str, sport, start, end) -> pd.DataFrame:
    with db.connect(db_path) as con:
        return queries.activities(con, sport, start, end)


def run_import() -> None:
    with db.connect(cfg.db_path) as con:
        st.session_state["scan_result"] = scan(con, cfg)
    st.cache_data.clear()


LABELS = {"ftp": "FTP (W)", "threshold_hr": "Threshold HR (bpm)", "max_hr": "Max HR (bpm)"}


def thresholds_panel() -> None:
    """Add/replace/delete dated thresholds; affected activities are rescored."""
    with db.connect(cfg.db_path) as con:
        entries = db.list_thresholds(con)
    with st.expander("Thresholds", expanded=not entries):
        st.caption("Each value applies from its date onward; earlier activities keep earlier values.")
        with st.form("threshold_form", clear_on_submit=False):
            metric = st.selectbox("Metric", list(LABELS), format_func=LABELS.get, key="th_metric")
            eff = st.date_input("Effective from", value=date.today(), key="th_date")
            value = st.number_input("Value", value=250.0, step=1.0, key="th_value")
            submitted = st.form_submit_button("Save", key="th_submit")
        if submitted:
            try:
                with db.connect(cfg.db_path) as con:
                    n = save_threshold(con, metric, eff, value)
            except ValueError as e:
                st.error(str(e))
            else:
                st.cache_data.clear()
                st.session_state["flash"] = f"Saved {LABELS[metric]} = {value:g} from {eff}; rescored {n} activities."
                st.rerun()
        if entries:
            st.dataframe(pd.DataFrame(entries, columns=["metric", "effective from", "value"]),
                         hide_index=True, width="stretch")
            pick = st.selectbox("Delete entry", entries, key="th_delete_pick",
                                format_func=lambda e: f"{LABELS[e[0]]} from {e[1]}: {e[2]:g}")
            if st.button("Delete", key="th_delete"):
                with db.connect(cfg.db_path) as con:
                    n = remove_threshold(con, pick[0], pick[1])
                st.cache_data.clear()
                st.session_state["flash"] = f"Deleted; rescored {n} activities."
                st.rerun()


# --- import on first load of the session, and on demand ----------------------------------------

if "scanned" not in st.session_state:
    st.session_state["scanned"] = True
    try:
        with db.connect(cfg.db_path) as con:
            seed_thresholds(con, cfg.thresholds)
    except ValueError as e:
        st.error(f"Config thresholds rejected: {e}")
    run_import()

DB = str(cfg.db_path)
st.title("Training status")
if "flash" in st.session_state:
    st.success(st.session_state.pop("flash"))

with st.sidebar:
    st.header("Filters")
    sport_choice = st.selectbox("Sport", ["All"] + load_sports(DB))
    sport = None if sport_choice == "All" else sport_choice
    full = load_pmc(DB, None, None, None)
    first = full["date"].min() if not full.empty else date.today() - timedelta(days=180)
    default_start = max(first, date.today() - timedelta(days=180))
    picked = st.date_input("Date range", value=(default_start, date.today()),
                           min_value=first, max_value=date.today())
    start, end = (picked if isinstance(picked, tuple) and len(picked) == 2 else (default_start, date.today()))
    thresholds_panel()
    if st.button("Import now", key="import_now", width="stretch"):
        run_import()
        st.rerun()
    res = st.session_state.get("scan_result")
    if res is not None:
        if res.folder_missing:
            st.warning(f"FIT folder not found: `{cfg.fit_dir}`")
        else:
            st.caption(f"Last import: {res.summary()}")
            for name, reason in res.failures:
                st.caption(f":red[{name}]: {reason}")

# --- empty state --------------------------------------------------------------------------------

if full.empty:
    st.info(
        f"No activities yet. Put FIT files in `{cfg.fit_dir}` "
        "(set `MYFITTY_FIT_DIR` to change it) and press **Import now**."
    )
    st.stop()

# --- charts -------------------------------------------------------------------------------------

pmc = load_pmc(DB, sport, start, end)
weekly = load_weekly(DB, sport, start, end)
x = alt.X("date:T", title=None)

st.subheader("Fitness and fatigue")
long = pmc.melt("date", ["ctl", "atl"], var_name="metric", value_name="value")
long["metric"] = long["metric"].map({"ctl": "Fitness (CTL)", "atl": "Fatigue (ATL)"})
color = alt.Color("metric:N", title=None, sort=["Fitness (CTL)", "Fatigue (ATL)"],
                  scale=alt.Scale(domain=["Fitness (CTL)", "Fatigue (ATL)"], range=[CTL_COLOR, ATL_COLOR]),
                  legend=alt.Legend(orient="top", direction="horizontal"))
hover = alt.selection_point(fields=["date"], nearest=True, on="pointerover", empty=False, clear="pointerout")
lines = alt.Chart(long).mark_line(strokeWidth=2).encode(x=x, y=alt.Y("value:Q", title="TSS / day (weighted)"), color=color)
points = lines.mark_point(size=60, filled=True).encode(opacity=alt.condition(hover, alt.value(1), alt.value(0)))
rule = alt.Chart(long).mark_rule(color="gray", opacity=0.4).encode(
    x=x, tooltip=[alt.Tooltip("date:T"), alt.Tooltip("metric:N"), alt.Tooltip("value:Q", format=".1f")],
    opacity=alt.condition(hover, alt.value(1), alt.value(0))).add_params(hover)
st.altair_chart((lines + points + rule).properties(height=280), width="stretch")

st.subheader("Form (TSB = CTL − ATL)")
area = alt.Chart(pmc).mark_area(opacity=0.25, color=TSB_COLOR, line={"color": TSB_COLOR, "strokeWidth": 2}).encode(
    x=x, y=alt.Y("tsb:Q", title="TSB"), tooltip=[alt.Tooltip("date:T"), alt.Tooltip("tsb:Q", format=".1f")])
zero = alt.Chart(pd.DataFrame({"y": [0]})).mark_rule(color="gray", strokeDash=[4, 4]).encode(y="y:Q")
st.altair_chart((area + zero).properties(height=160), width="stretch")

st.subheader("Weekly load")
bars = alt.Chart(weekly).mark_bar(color=CTL_COLOR, cornerRadiusTopLeft=4, cornerRadiusTopRight=4).encode(
    x=alt.X("week_start:T", title="Week starting (Monday)"), y=alt.Y("tss:Q", title="TSS"),
    tooltip=[alt.Tooltip("week_start:T", title="Week of"), alt.Tooltip("tss:Q", title="TSS", format=".0f")])
st.altair_chart(bars.properties(height=200), width="stretch")

st.subheader("Activities")
acts = load_activities(DB, sport, start, end)
table = acts.assign(
    when=acts["start_time"].dt.strftime("%Y-%m-%d %H:%M"),
    minutes=(acts["moving_seconds"] / 60).round(0),
    km=(acts["distance_m"] / 1000).round(1),
)[["when", "sport", "sub_sport", "minutes", "km", "tss", "tss_method", "trimp", "unscored_reason"]]
st.dataframe(table.rename(columns={"tss": "TSS", "tss_method": "method", "trimp": "relative effort",
                                   "unscored_reason": "unscored"}),
             hide_index=True, width="stretch")
