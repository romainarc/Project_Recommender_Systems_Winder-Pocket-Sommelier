"""Pocket Sommelier frontend (owner: SE).

1. The user answers the taste questionnaire  -> POST /onboard
2. They pick a dish and get wines             -> POST /recommend (trained model)
3. like / dislike / cellar on a wine          -> POST /log_interaction, the list updates

Run (API must be running):  streamlit run app/streamlit_app.py
"""
import os
import uuid

import requests
import streamlit as st

API = os.environ.get("API_URL", "http://localhost:8000")

st.set_page_config(page_title="Pocket Sommelier", page_icon="🍷")
st.title("Pocket Sommelier")
st.caption("Tell us your taste, pick your dish, get the right wine.")

try:
    options = requests.get(f"{API}/options", timeout=10).json()
    health = requests.get(f"{API}/health", timeout=10).json()
except requests.RequestException:
    st.error(f"API not reachable at {API}. Start it with: uvicorn api.main:app")
    st.stop()

if "user_id" not in st.session_state:
    st.session_state.user_id = "app-" + uuid.uuid4().hex[:8]
    st.session_state.onboarded = False
user_id = st.session_state.user_id

# ------------------------------------------------------------------ 1. questionnaire
with st.expander("1. Your taste", expanded=not st.session_state.onboarded):
    with st.form("questionnaire"):
        color = st.selectbox("Favourite colour", ["(no preference)"] + options["color"])
        body = st.selectbox("Light or full-bodied?", ["(no preference)"] + options["body"])
        acidity = st.selectbox("Acidity", ["(no preference)"] + options["acidity"])
        grapes = st.multiselect("Grapes you like", options["grapes"], max_selections=3)
        countries = st.multiselect("Countries you like", options["countries"], max_selections=2)
        discovery = st.radio("You prefer", ["safe", "explorer"],
                             format_func=lambda x: "safe choices" if x == "safe" else "to discover",
                             horizontal=True)
        if st.form_submit_button("Save my taste"):
            pick = lambda v: None if v == "(no preference)" else v
            requests.post(f"{API}/onboard", timeout=30, json={
                "user_id": user_id, "color": pick(color), "body": pick(body),
                "acidity": pick(acidity), "grapes": grapes, "countries": countries,
                "discovery": discovery})
            st.session_state.onboarded = True
            st.rerun()

# ------------------------------------------------------------------ 2. recommendations
st.subheader("2. Your wines")
dish = st.selectbox("What are you eating?", ["(any)"] + options["dishes"])
payload = {"user_id": user_id, "dish": None if dish == "(any)" else dish, "k": 10}
res = requests.post(f"{API}/recommend", json=payload, timeout=30).json()
st.caption(f"model {res['model_version']} · answered in {res['latency_ms']:.0f} ms · user {user_id}")

def log_event(user_id, wine_id, event_type, label, dish):
    """Button callback (idea from PR #2): it runs BEFORE Streamlit's rerun, so the click is
    always logged, and the rerun that follows shows the updated list."""
    try:
        requests.post(f"{API}/log_interaction", timeout=30, json={
            "user_id": user_id, "wine_id": wine_id, "event_type": event_type, "dish": dish})
        st.toast(f"{label} saved, your list is updated")
    except requests.RequestException:
        st.toast("Could not reach the API, feedback not saved")


for w in res["wines"]:
    with st.container(border=True):
        st.markdown(f"**{w['name']}** · {w['type']} · {w.get('body') or ''} · "
                    f"{', '.join(w['grapes'][:3])} · {w['country']}")
        st.caption(w["explanation"])
        c1, c2, c3 = st.columns(3)
        for col, evt, label in ((c1, "like", "👍 like"), (c2, "dislike", "👎 dislike"),
                                (c3, "add_to_cellar", "🍾 cellar")):
            col.button(label, key=f"{evt}-{w['wine_id']}", on_click=log_event,
                       args=(user_id, w["wine_id"], evt, label, payload["dish"]))
