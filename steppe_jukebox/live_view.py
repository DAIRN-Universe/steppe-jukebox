"""Streamlit transport for the single, existing route-player component."""
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from . import __version__
from .eic import FrameClient, cache_directory
from .gibs import TileCache, user_cache_directory
from .live import LiveJob, load_live_regions, player_catalog

player = components.declare_component("route_player", path=str(Path(__file__).parent / "frontend"))


@st.cache_resource(show_spinner=False)
def environment(version):
    # New releases must not reuse metadata/translations from the previous UI.
    regions = load_live_regions()
    return regions, player_catalog(regions)


def render_live():
    regions, catalog = environment(__version__)
    job = st.session_state.get("live-job")
    request = job.payload(st.session_state.get("live-known", {})) if job else None
    if request and request["source"] == "eic" and request["available_dates"] and not st.session_state.get("live-catalog-dates"):
        st.session_state["live-catalog-dates"] = request["available_dates"]
    payload = {"live": True, "base": catalog, "ack": st.session_state.get("live-command"),
               "cache": {"gibs": str(user_cache_directory()), "eic": str(cache_directory())},
               "catalog_dates": st.session_state.get("live-catalog-dates", []),
               "catalog_error": st.session_state.get("live-catalog-error", False),
               "request": request}
    command = player(payload=payload, key="route-player", default=None)
    if not isinstance(command, dict) or command.get("id") == st.session_state.get("live-command"):
        return
    st.session_state["live-command"] = command.get("id")
    if command.get("type") in {"load", "invalidate", "clear"}:
        if job:
            job.cancel()
        st.session_state["live-job"] = None
        st.session_state["live-known"] = {}
        if command["type"] == "clear":
            if command.get("source") == "eic":
                FrameClient().clear()
                st.session_state["live-catalog-dates"] = []
                st.session_state["live-catalog-error"] = False
            elif command.get("source") == "gibs":
                TileCache().clear()
        if command["type"] == "load":
            region = regions.get(command.get("region"))
            if region is not None:
                try:
                    st.session_state["live-job"] = LiveJob(command["id"], region, command.get("source"),
                                                         command.get("mode"), command.get("date"),
                                                         layers={k: bool(command.get(k)) for k in ["snow", "water", "temperature"]}).start()
                except (ValueError, TypeError):
                    pass
    elif command.get("type") == "poll":
        known = command.get("known")
        if isinstance(known, dict):
            st.session_state["live-known"] = known
    elif command.get("type") == "refresh_catalog":
        try:
            st.session_state["live-catalog-dates"] = FrameClient().catalog(refresh=True)
            st.session_state["live-catalog-error"] = False
        except (OSError, ValueError):
            st.session_state["live-catalog-error"] = True
    st.rerun()
