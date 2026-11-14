"""Run with: python -m streamlit run app.py"""

import os
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from steppe_jukebox import __version__
from steppe_jukebox.data import DataError, load_dataset
from steppe_jukebox.player import error_payload, player_payload, regions_payload
from steppe_jukebox.regions import load_regions


ROOT = Path(__file__).resolve().parent
st.set_page_config(page_title="Steppe Jukebox", page_icon="🌱", layout="wide")
st.caption(f"v{__version__}")


@st.cache_data(show_spinner=False)
def prepare_player(data):
    return player_payload(data)


@st.cache_data(show_spinner=False)
def prepare_regions(regions):
    return regions_payload(regions)


player = components.declare_component("route_player", path=str(ROOT / "steppe_jukebox" / "frontend"))
try:
    if directory := os.environ.get("STEPPE_DATA_DIR"):
        payload = prepare_player(load_dataset(Path(directory)))
    else:
        payload = prepare_regions(load_regions(ROOT / "data" / "regions.json"))
except DataError as error:
    payload = error_payload(error)

# Keep all app-owned text in one component: language changes need no server
# rerun and cannot interrupt the transport. CSV errors retain the language picker.
player(payload=payload, key="route-player", default=None)
