"""Pocket Sommelier frontend (owner: SE).

1. The user answers the taste questionnaire (sidebar)  -> POST /onboard
2. They pick a dish and get wines                       -> POST /recommend (trained model)
3. Like / Not for me / Add to cellar on a wine          -> POST /log_interaction, the list updates

Run (API must be running):  streamlit run app/streamlit_app.py
The colours come from .streamlit/config.toml (light theme, wine accent).
"""
import html
import os
import uuid

import requests
import streamlit as st

API = os.environ.get("API_URL", "http://localhost:8000")

st.set_page_config(page_title="Pocket Sommelier", layout="wide", initial_sidebar_state="expanded")

#  style CSS
st.markdown("""
<style>
.block-container { padding-top: 3.2rem; max-width: 1200px; }
.hero { background: linear-gradient(120deg, #4a0f1d 0%, #7a1f33 60%, #a8455a 100%);
        color: #fff; border-radius: 16px; padding: 1.6rem 2rem; margin-bottom: 1.2rem; }
.hero h1 { color: #fff; font-size: 2.1rem; margin: 0 0 .3rem 0; letter-spacing: .3px; }
.hero p { color: #f3dfe3; margin: 0; font-size: 1.02rem; }
.stats { display: flex; gap: .8rem; margin-top: 1rem; flex-wrap: wrap; }
.stat { background: rgba(255,255,255,.12); border: 1px solid rgba(255,255,255,.25);
        border-radius: 10px; padding: .45rem .8rem; font-size: .85rem; color: #fff; }
.stat b { font-size: 1rem; }
.card { border: 1px solid #eadfe2; border-radius: 14px; padding: 1rem 1.1rem .7rem 1.1rem;
        background: #fff; box-shadow: 0 1px 3px rgba(74,15,29,.06); height: 100%; }
.top { display: flex; justify-content: space-between; align-items: baseline; gap: .5rem; }
.num { color: #7a1f33; font-weight: 700; font-size: .95rem; }
.name { font-size: 1.05rem; font-weight: 650; color: #2a1a1e; margin: .15rem 0 .35rem 0; }
.chips { margin-bottom: .55rem; }
.chip { display: inline-block; background: #f4eef0; color: #5a3a42; border-radius: 999px;
        padding: .1rem .6rem; font-size: .78rem; margin: 0 .3rem .3rem 0; }
.badge { font-size: .72rem; border-radius: 999px; padding: .1rem .55rem; white-space: nowrap; }
.badge.pop { background: #fbecd9; color: #8a5a12; }
.badge.disc { background: #e3f0ea; color: #1f6b47; }
.why { border-left: 3px solid #7a1f33; background: #fbf6f7; color: #5a2230; padding: .4rem .6rem;
       font-size: .85rem; border-radius: 0 8px 8px 0; }
.meta { color: #8a7f82; font-size: .8rem; }
section[data-testid="stSidebar"] { background: #fbf6f7; border-right: 1px solid #eadfe2; }
div.stButton > button { border-radius: 999px; font-size: .82rem; padding: .2rem .4rem; width: 100%; }
</style>
""", unsafe_allow_html=True)

# API
try:
    options = requests.get(f"{API}/options", timeout=10).json()
    health = requests.get(f"{API}/health", timeout=10).json()
except requests.RequestException:
    st.error(f"The API is not reachable at {API}. Start it with: uvicorn api.main:app")
    st.stop()

if "user_id" not in st.session_state:
    st.session_state.user_id = "app-" + uuid.uuid4().hex[:8]
    st.session_state.onboarded = False
    st.session_state.feedback = 0
user_id = st.session_state.user_id

# 1. questionnaire (sidebar)
with st.sidebar:
    st.markdown("## Your taste")
    st.caption("A few answers are enough to start. Your likes refine the list after that.")
    with st.form("questionnaire"):
        color = st.selectbox("Colour", ["No preference"] + options["color"])
        body = st.selectbox("Body", ["No preference"] + options["body"])
        acidity = st.selectbox("Acidity", ["No preference"] + options["acidity"])
        grapes = st.multiselect("Grapes you like (up to 3)", options["grapes"], max_selections=3)
        countries = st.multiselect("Countries you like (up to 2)", options["countries"],
                                   max_selections=2)
        discovery = st.radio("You prefer", ["safe", "explorer"], horizontal=True,
                             format_func=lambda x: "Safe choices" if x == "safe" else "Discoveries")
        if st.form_submit_button("Save my taste", type="primary", use_container_width=True):
            pick = lambda v: None if v == "No preference" else v
            requests.post(f"{API}/onboard", timeout=30, json={
                "user_id": user_id, "color": pick(color), "body": pick(body),
                "acidity": pick(acidity), "grapes": grapes, "countries": countries,
                "discovery": discovery})
            st.session_state.onboarded = True
    if st.session_state.onboarded:
        st.success("Taste profile saved")
    st.markdown(f"<p class='meta'>Feedback given: {st.session_state.feedback} · "
                f"session {user_id}</p>", unsafe_allow_html=True)

# header
n_wines = health.get("wines") or health.get("n_wines")
stats = [f"<span class='stat'>Model <b>{html.escape(str(health.get('model_version', '')))}</b></span>",
         "<span class='stat'>Graph model <b>HGIB + KGAT</b></span>"]
if n_wines:
    stats.append(f"<span class='stat'><b>{int(n_wines):,}</b> wines</span>")
st.markdown(
    "<div class='hero'><h1>Pocket Sommelier</h1>"
    "<p>Tell us your taste, pick your dish, get the right wine. "
    "Every like teaches the sommelier a little more about you.</p>"
    f"<div class='stats'>{''.join(stats)}</div></div>", unsafe_allow_html=True)

if not st.session_state.onboarded:
    st.info("Start with your taste in the left panel. Until then, you see the wines people like most.")

# 2. recommendations
dish = st.selectbox("What are you eating tonight?", ["Any dish"] + options["dishes"])
k = 10
payload = {"user_id": user_id, "dish": None if dish == "Any dish" else dish, "k": k}
res = requests.post(f"{API}/recommend", json=payload, timeout=30).json()
st.markdown(f"<p class='meta'>{len(res['wines'])} wines · answered in "
            f"{res['latency_ms']:.0f} ms</p>", unsafe_allow_html=True)


def log_event(user_id, wine_id, event_type, label, dish):
    """Button callback: runs BEFORE Streamlit's rerun, so the click is always logged and the
    rerun that follows shows the updated list."""
    try:
        requests.post(f"{API}/log_interaction", timeout=30, json={
            "user_id": user_id, "wine_id": wine_id, "event_type": event_type, "dish": dish})
        st.session_state.feedback += 1
        st.toast(f"{label}: saved. Your list is updated.")
    except requests.RequestException:
        st.toast("Could not reach the API, feedback not saved.")


def card(i, w):
    rank = w.get("popularity_rank")
    badge = ""
    if rank is not None:
        badge = ("<span class='badge pop'>Popular pick</span>" if rank <= 200
                 else "<span class='badge disc'>Discovery</span>")
    chips = [w.get("type"), w.get("body"), w.get("country")] + list(w["grapes"][:2])
    chips_html = "".join(f"<span class='chip'>{html.escape(str(c))}</span>" for c in chips if c)
    return (f"<div class='card'><div class='top'><span class='num'>#{i}</span>{badge}</div>"
            f"<div class='name'>{html.escape(w['name'])}</div>"
            f"<div class='chips'>{chips_html}</div>"
            f"<div class='why'>{html.escape(w['explanation'])}</div></div>")


wines = res["wines"]
for start in range(0, len(wines), 2):
    cols = st.columns(2, gap="medium")
    for col, (i, w) in zip(cols, list(enumerate(wines, start=1))[start:start + 2]):
        with col:
            st.markdown(card(i, w), unsafe_allow_html=True)
            b1, b2, b3 = st.columns(3)
            for bc, evt, label in ((b1, "like", "Like"), (b2, "dislike", "Not for me"),
                                   (b3, "add_to_cellar", "Add to cellar")):
                bc.button(label, key=f"{evt}-{w['wine_id']}", on_click=log_event,
                          args=(user_id, w["wine_id"], evt, label, payload["dish"]))
    st.write("")
