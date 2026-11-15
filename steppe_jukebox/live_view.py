"""Streamlit transport for the single, existing route-player component."""
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from . import __version__
from .eic import FrameClient, cache_directory
from .gibs import TileCache, user_cache_directory
from .live import LiveJob, load_live_regions, player_catalog
from .nasa_grid import display_grid
from .routing import RouteError, build_path, route_definition, route_region

player = components.declare_component("route_player", path=str(Path(__file__).parent / "frontend"))


@st.cache_resource(show_spinner=False)
def environment(version):
    # New releases must not reuse metadata/translations from the previous UI.
    regions = load_live_regions()
    return regions, player_catalog(regions)


def render_live():
    regions, catalog = environment(__version__)
    job = st.session_state.get("live-job")
    request = job.payload(st.session_state.get("live-known", {})) if job else st.session_state.get("live-error")
    if request and request["source"] == "eic" and request["available_dates"] and not st.session_state.get("live-catalog-dates"):
        st.session_state["live-catalog-dates"] = request["available_dates"]
    payload = {"live": True, "base": catalog, "ack": st.session_state.get("live-command"),
               "route_result": st.session_state.get("route-result"),
               "cache": {"gibs": str(user_cache_directory()), "eic": str(cache_directory())},
               "catalog_dates": st.session_state.get("live-catalog-dates", []),
               "catalog_error": st.session_state.get("live-catalog-error", False),
               "request": request}
    command = player(payload=payload, key="route-player", default=None)
    if not isinstance(command, dict) or command.get("id") == st.session_state.get("live-command"):
        return
    st.session_state["live-command"] = command.get("id")
    if command.get("type") == "build_route":
        result = {"id": command["id"], "region": command.get("region")}
        try:
            region = regions.get(command.get("region"))
            if region is None:
                raise RouteError("outside")
            cells = display_grid(region.grid, ())['cells']
            path = build_path(cells, command.get("waypoints"))
            custom = route_region(region, cells, path)
            # Keep the previous committed route usable if a subsequent draft fails.
            routes = st.session_state.setdefault("session-routes", {})
            routes[command["id"]] = custom
            # Bound abandoned draft results while retaining recent committed tokens.
            while len(routes) > 16:
                oldest = next(iter(routes))
                if oldest == st.session_state.get("loaded-route-token"):
                    routes[oldest] = routes.pop(oldest)
                else:
                    del routes[oldest]
            result["definition"] = route_definition(custom, cells, path)
        except RouteError as error:
            result.update(error=error.code, key=error.key)
        st.session_state["route-result"] = result
    elif command.get("type") in {"load", "invalidate", "clear"}:
        if job:
            job.cancel()
        st.session_state["live-job"] = None
        st.session_state["live-error"] = None
        st.session_state["live-known"] = {}
        if command["type"] == "clear":
            if command.get("source") == "eic":
                FrameClient().clear()
                st.session_state["live-catalog-dates"] = []
                st.session_state["live-catalog-error"] = False
            elif command.get("source") == "gibs":
                TileCache().clear()
        if command["type"] == "load":
            try:
                region = regions.get(command.get("region"))
                token = command.get("route_token")
                if token is not None:
                    region = st.session_state.get("session-routes", {}).get(token)
                if region is None or region.key != command.get("region") or command.get("mode") != "fixed":
                    raise ValueError("Invalid session route or mode")
                st.session_state["live-job"] = LiveJob(command["id"], region, command.get("source"),
                                                     command.get("mode"), command.get("date"),
                                                     layers={"snow": bool(command.get("snow")), "temperature": bool(command.get("temperature")), "water": False}).start()
                st.session_state["loaded-route-token"] = token
            except (ValueError, TypeError):
                st.session_state["live-error"] = {
                    "id": command["id"], "source": command.get("source"), "state": "error", "error": "request_error",
                    "available_dates": [], "maps": [], "track": None, "missing_dates": [], "route_errors": [],
                    "network_requests": 0, "completed_dates": 0, "total_dates": 0, "tile_errors": 0}
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
