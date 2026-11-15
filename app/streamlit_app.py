"""Pocket Sommelier frontend (owner: SE). Week 2: calls the API, which returns mock lists.

Run (API must be running):  streamlit run app/streamlit_app.py
"""
import os

import requests
import streamlit as st

API = os.environ.get("API_URL", "http://localhost:8000")

st.set_page_config(page_title="Pocket Sommelier", page_icon="🍷")
st.title("Pocket Sommelier")
st.caption("The right wine for you and the dish on your plate.")

user_id = st.text_input("Your user id", value="demo-user")
try:
    dishes = requests.get(f"{API}/dishes", timeout=5).json()["dishes"]
except requests.RequestException:
    st.error(f"API not reachable at {API}. Start it with: uvicorn api.main:app")
    st.stop()
dish = st.selectbox("What are you eating?", ["(any)"] + dishes)

if st.button("Recommend"):
    payload = {"user_id": user_id, "dish": None if dish == "(any)" else dish, "k": 10}
    res = requests.post(f"{API}/recommend", json=payload, timeout=5).json()
    st.caption(f"model: {res['model_version']}")
    for w in res["wines"]:
        with st.container(border=True):
            st.markdown(f"**{w['name']}** · {w['type']} · {', '.join(w['grapes'])} · {w['country']}")
            st.caption(w["explanation"])
            c1, c2, c3 = st.columns(3)
            for col, evt in zip((c1, c2, c3), ("like", "dislike", "add_to_cellar")):
                if col.button(evt.replace("_", " "), key=f"{evt}-{w['wine_id']}"):
                    requests.post(f"{API}/log_interaction", timeout=5, json={
                        "user_id": user_id, "wine_id": w["wine_id"], "event_type": evt,
                        "dish": payload["dish"]})
                    st.toast(f"{evt} logged")
