"""Run with: python -m streamlit run app.py"""

import os
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from steppe_jukebox.data import DataError, load_dataset
from steppe_jukebox.player import error_payload, player_payload, regions_payload
from steppe_jukebox.regions import load_regions
from steppe_jukebox.live_view import render_live


ROOT = Path(__file__).resolve().parent
st.set_page_config(page_title="Steppe Jukebox", page_icon="🌱", layout="wide")
# Keep the toolbar clear and reclaim side gutters for the instrument.
st.html("<style>[data-testid='stMainBlockContainer'] { padding-top: 4rem; padding-inline: clamp(1rem, 3vw, 3rem); }</style>")


@st.cache_data(show_spinner=False)
def prepare_player(data):
    return player_payload(data)


@st.cache_data(show_spinner=False)
def prepare_regions(regions):
    return regions_payload(regions)


if not os.environ.get("STEPPE_DATA_DIR") and not os.environ.get("STEPPE_SAVED_REGIONS"):
    render_live()
else:
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
