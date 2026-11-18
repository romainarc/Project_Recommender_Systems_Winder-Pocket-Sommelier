"""Pocket Sommelier frontend (owner: SE). Week 2: calls the API, which returns mock lists.

Run (API must be running):  streamlit run app/streamlit_app.py

The recommendation list is kept in st.session_state, so it survives the rerun that Streamlit
triggers when a like / dislike / cellar button is clicked, and the click is actually logged.
"""
import os

import requests
import streamlit as st

API = os.environ.get("API_URL", "http://localhost:8000")

st.set_page_config(page_title="Pocket Sommelier", page_icon="🍷")
st.title("Pocket Sommelier")
st.caption("The right wine for you and the dish on your plate.")

st.session_state.setdefault("recs", None)       # last /recommend response
st.session_state.setdefault("feedback", {})     # wine_id -> last event logged


def log_event(user_id: str, wine_id: int, event_type: str, dish):
    """Button callback: runs before the rerun, so the event is never lost."""
    try:
        requests.post(f"{API}/log_interaction", timeout=5, json={
            "user_id": user_id, "wine_id": wine_id, "event_type": event_type, "dish": dish})
        st.session_state.feedback[wine_id] = event_type
        st.toast(f"{event_type.replace('_', ' ')} logged")
    except requests.RequestException:
        st.toast("Could not reach the API, event not logged")


user_id = st.text_input("Your user id", value="demo-user")
try:
    dishes = requests.get(f"{API}/dishes", timeout=5).json()["dishes"]
except requests.RequestException:
    st.error(f"API not reachable at {API}. Start it with: uvicorn api.main:app")
    st.stop()
dish = st.selectbox("What are you eating?", ["(any)"] + dishes)

if st.button("Recommend", type="primary"):
    payload = {"user_id": user_id, "dish": None if dish == "(any)" else dish, "k": 10}
    st.session_state.recs = requests.post(f"{API}/recommend", json=payload, timeout=5).json()
    st.session_state.feedback = {}

res = st.session_state.recs
if res:
    st.caption(f"model: {res['model_version']} · dish: {res['dish'] or 'any'}")
    for w in res["wines"]:
        done = st.session_state.feedback.get(w["wine_id"])
        with st.container(border=True):
            st.markdown(f"**{w['name']}** · {w['type']} · {', '.join(w['grapes'])} · {w['country']}")
            st.caption(w["explanation"])
            cols = st.columns(3)
            for col, evt in zip(cols, ("like", "dislike", "add_to_cellar")):
                label = evt.replace("_", " ")
                col.button(f"✓ {label}" if done == evt else label,
                           key=f"{evt}-{w['wine_id']}",
                           on_click=log_event,
                           args=(res["user_id"], w["wine_id"], evt, res["dish"]))
