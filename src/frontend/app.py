import os

import requests
import streamlit as st

BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")

st.set_page_config(page_title="Go Game Review Analyser", layout="wide")


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def _auth_headers() -> dict:
    return {"Authorization": f"Bearer {st.session_state.get('token', '')}"}


def _error_detail(resp, fallback: str) -> str:
    try:
        return resp.json().get("detail", fallback)
    except Exception:
        return f"{fallback} (HTTP {resp.status_code}): {resp.text or 'no response body'}"


def _login(username: str, password: str) -> bool:
    resp = requests.post(
        f"{BACKEND_URL}/auth/token",
        data={"username": username, "password": password},
    )
    if resp.status_code == 200:
        st.session_state["token"] = resp.json()["access_token"]
        st.session_state["username"] = username
        return True
    return False


def _register(username: str, password: str) -> tuple[bool, str]:
    resp = requests.post(
        f"{BACKEND_URL}/auth/register",
        json={"username": username, "password": password},
    )
    if resp.status_code == 201:
        return True, ""
    try:
        detail = resp.json().get("detail", "Registration failed")
    except Exception:
        detail = f"Registration failed (HTTP {resp.status_code}): {resp.text or 'no response body'}"
    return False, detail


# ---------------------------------------------------------------------------
# Auth page
# ---------------------------------------------------------------------------

def _show_auth_page():
    st.title("Go Game Review Analyser")
    tab_login, tab_register = st.tabs(["Log in", "Register"])

    with tab_login:
        username = st.text_input("Username", key="login_user")
        password = st.text_input("Password", type="password", key="login_pass")
        if st.button("Log in"):
            if _login(username, password):
                st.rerun()
            else:
                st.error("Invalid username or password")

    with tab_register:
        new_user = st.text_input("Username", key="reg_user")
        new_pass = st.text_input("Password", type="password", key="reg_pass")
        if st.button("Register"):
            ok, msg = _register(new_user, new_pass)
            if ok:
                st.success("Account created — please log in")
            else:
                st.error(msg)


# ---------------------------------------------------------------------------
# Main app
# ---------------------------------------------------------------------------

def _show_main_app():
    st.sidebar.write(f"Logged in as **{st.session_state.get('username')}**")
    if st.sidebar.button("Log out"):
        st.session_state.clear()
        st.rerun()

    st.title("Go Game Review Analyser")

    _section_upload()
    st.divider()
    _section_analyses()


def _section_upload():
    st.header("Upload game reviews")
    files = st.file_uploader(
        "Upload one or more markdown review files",
        type=["md"],
        accept_multiple_files=True,
    )
    if files:
        if st.button("Process uploaded files"):
            with st.spinner("Extracting structured fields via Claude..."):
                resp = requests.post(
                    f"{BACKEND_URL}/upload",
                    headers=_auth_headers(),
                    files=[("files", (f.name, f.getvalue(), "text/markdown")) for f in files],
                )
            if resp.status_code == 200:
                data = resp.json()
                st.success(data["message"])
            else:
                st.error(_error_detail(resp, "Upload failed"))


def _section_analyses():
    st.header("Analysis")

    if st.button("Run analysis on current batch"):
        with st.spinner("Running Stage 2 + Stage 3 analysis via Claude..."):
            resp = requests.post(
                f"{BACKEND_URL}/analyse",
                headers=_auth_headers(),
            )
        if resp.status_code == 200:
            st.success("Analysis complete")
            st.rerun()
        else:
            st.error(_error_detail(resp, "Analysis failed"))

    # Fetch all analyses for the browser and win-rate chart
    analyses_resp = requests.get(f"{BACKEND_URL}/analyses", headers=_auth_headers())
    if analyses_resp.status_code != 200 or not analyses_resp.json():
        st.info("No analyses yet. Upload at least 20 game reviews and run an analysis.")
        return

    analyses = analyses_resp.json()
    _show_win_rate_chart(analyses)
    st.divider()

    # Analysis browser
    options = {
        f"{a['period_start']} → {a['period_end']}  ({a['win_count']}/{a['game_count']} wins)": a
        for a in analyses
    }
    selected_label = st.selectbox("View analysis", list(options.keys()))
    selected = options[selected_label]

    col_del, _ = st.columns([1, 5])
    with col_del:
        if st.button("Delete this analysis", type="secondary"):
            del_resp = requests.delete(
                f"{BACKEND_URL}/analyses/{selected['id']}",
                headers=_auth_headers(),
            )
            if del_resp.status_code == 204:
                st.success("Analysis deleted")
                st.rerun()
            else:
                st.error(_error_detail(del_resp, "Delete failed"))

    # Fetch full detail for the selected analysis
    detail_resp = requests.get(
        f"{BACKEND_URL}/analyses/{selected['id']}", headers=_auth_headers()
    )
    if detail_resp.status_code != 200:
        st.error(_error_detail(detail_resp, "Could not load analysis"))
        return
    detail = detail_resp.json()

    _show_recurring_patterns(detail.get("notes_analysis") or {})
    st.divider()
    _show_playing_style(detail.get("playing_style") or {})

    # Tag charts
    st.divider()
    tag_resp = requests.get(f"{BACKEND_URL}/analyses/tag-stats", headers=_auth_headers())
    if tag_resp.status_code == 200:
        _show_tag_charts(tag_resp.json())

    # Progress comparison (only if comparison exists)
    comparison = detail.get("comparison")
    if comparison:
        st.divider()
        _show_progress(comparison)


def _show_win_rate_chart(analyses: list[dict]):
    st.subheader("Win rate over time")
    import pandas as pd

    rows = [
        {
            "Batch end": a["period_end"] or a["created_at"][:10],
            "Win rate": a["win_count"] / a["game_count"] if a["game_count"] else 0,
            "Games": a["game_count"],
        }
        for a in reversed(analyses)
        if a.get("game_count")
    ]
    if rows:
        df = pd.DataFrame(rows).set_index("Batch end")
        st.line_chart(df["Win rate"])


def _show_recurring_patterns(notes_analysis: dict):
    st.subheader("Recurring patterns")

    overall = notes_analysis.get("overall_impression")
    if overall:
        st.info(overall)

    mistakes = notes_analysis.get("recurring_mistakes") or []
    if mistakes:
        st.markdown("**Recurring mistakes**")
        for m in mistakes:
            with st.expander(m.get("pattern", "—")):
                st.markdown(f"*Why:* {m.get('cause_hypothesis', '')}")
                st.markdown(f"*Focus:* {m.get('focus', '')}")

    strengths = notes_analysis.get("recurring_strengths") or []
    if strengths:
        st.markdown("**Recurring strengths**")
        for s in strengths:
            with st.expander(s.get("pattern", "—")):
                st.markdown(f"*Why:* {s.get('cause_hypothesis', '')}")


def _show_playing_style(playing_style: dict):
    st.subheader("Playing style")
    if not playing_style:
        st.write("—")
        return
    dimensions = [
        "Knowledge", "Reading", "Territorial Intuition", "Technical Intuition",
        "Strategy", "Game Experience", "Mind Control",
    ]
    for dim in dimensions:
        assessment = playing_style.get(dim)
        if assessment:
            with st.expander(dim):
                st.write(assessment)


def _show_tag_charts(tag_stats: dict):
    st.subheader("Tag breakdown")
    import pandas as pd

    col_all, col_win, col_loss = st.columns(3)

    for col, label, key in [
        (col_all, "All games", "all"),
        (col_win, "Wins", "wins"),
        (col_loss, "Losses", "losses"),
    ]:
        with col:
            st.markdown(f"**{label}**")
            counts = tag_stats.get(key) or {}
            if counts:
                df = (
                    pd.Series(counts)
                    .sort_values(ascending=False)
                    .head(10)
                    .to_frame("Count")
                )
                st.bar_chart(df)
            else:
                st.write("—")


def _show_progress(comparison: dict):
    st.subheader("Progress since last batch")

    progress = comparison.get("progress") or {}
    tag_trends = comparison.get("tag_trends") or {}

    col_imp, col_same, col_reg = st.columns(3)

    with col_imp:
        st.markdown("**Improved**")
        for item in progress.get("improved") or []:
            st.success(item)

    with col_same:
        st.markdown("**Same**")
        for item in progress.get("same") or []:
            st.info(item)

    with col_reg:
        st.markdown("**Regressed**")
        for item in progress.get("regressed") or []:
            st.warning(item)

    # Tag trends
    appeared = tag_trends.get("appeared") or []
    disappeared = tag_trends.get("disappeared") or []
    changed = tag_trends.get("changed") or []

    if appeared or disappeared or changed:
        st.markdown("**Tag trends**")
        if appeared:
            st.markdown("*New this batch:* " + ", ".join(t["tag"] for t in appeared))
        if disappeared:
            st.markdown("*No longer appearing:* " + ", ".join(t["tag"] for t in disappeared))
        if changed:
            for t in changed:
                direction = "up" if t["diff"] > 0 else "down"
                st.markdown(f"- **{t['tag']}**: {t['prev']} → {t['curr']} ({direction})")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if "token" not in st.session_state:
    _show_auth_page()
else:
    _show_main_app()
