# Steppe Jukebox

A DAIRN Great Steppe project for the [2026 NASA Space Apps Challenge: The Earth Information Jukebox](https://www.spaceappschallenge.org/2026/challenges/the-earth-information-jukebox/).

Steppe Jukebox lets people see and hear how vegetation varies along routes across Kazakhstan's Kostanay and Akmola regions. It loads NASA GIBS NOAA-20/VIIRS or NASA EIC Suomi NPP/VIIRS visualizations and turns vegetation-index color classes into notes while highlighting the corresponding cells on a map.

## First working version

- Compare spring and summer along the same route. Planned map landmarks include Kamennoye Lake, Naurzum, and Akkum in the Altyn Dala reserve.
- Use the same five-note scale, route, and tempo for both frames. Missing data are represented by silence.
- Show the original frame, date, and color legend. The notes represent color classes from the published visualization, not precise NDVI measurements.
- Run as a Python and Streamlit application with keyboard-accessible playback. Add autumn and winter after validating the first comparison.

## Status

**v0.6.0** adds editable routes to the Minimal Instrument interface. Pick **1–5 points** on the existing region grid; the application connects them in order and prepares a track for one exact date using **NASA GIBS / NOAA-20** or **NASA EIC / Suomi NPP**. Water does not restrict the route and no water mask is requested. Region boundaries and holes remain enforced. Each step uses the same five-note scale, 120 BPM and 0.5-second interval; missing NDVI produces silence.

The default routes retain their original geometry and timing: **Kostanay — 48 steps / 24 seconds**, **Akmola — 56 / 28 seconds**. Kostanay starts with three numbered place markers: **Kamennoye Lake → Naurzum → Akkum**. Akmola starts with its four established landmarks. The upcoming path stays hidden; playback and seeking reveal the current cell and travelled trail.

The **Route points** panel sits below **Load route**, starts collapsed and shows the point count in its heading. Zoom from **100% to 800%** using buttons, the mouse wheel or a two-finger pinch, and drag the enlarged map. Zooming, panning and collapsing the panel preserve the route and playback position. There is one audio player and no autoplay. Kazakh, English and Russian, keyboard controls, seek buttons and the compact mobile layout remain available.

Classes describe the selected visualization’s color scale, not precise numerical NDVI. GIBS and EIC have separate scales and caches; a missing date is reported without substituting another date or provider. The main interface uses **one date**. Historical seasonal datasets and journeys remain available explicitly in saved-data mode, with their original CSV/WAV contracts.

The user accepted the local application and authorized merging the changes into `main` and preparing **0.6.0** for publication. See [the release report](docs/RELEASE_0.6.0.md) for verification and known limits, and [the route acceptance report](docs/ISSUE_17_LOCAL.md) for detailed scenarios. Screen-reader and student evaluation remain separate work. EIC’s first download retrieves a global frame and can take around two minutes on the tested connection; a prepared cache needs no network access for the same inputs.

## Run the preview

Python 3.11 or newer:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Open `http://localhost:8501`. Select **Region**, **Data source** and an exact **Date**, press **Load route**, then start playback. For an initial comparison, use April 20 or June 10, 2026; both are in the checked EIC catalog. The collapsible **Route points** panel sits below **Load route**, starts folded with a point counter, and contains the preset’s named places: **Kamennoye Lake → Naurzum → Akkum** (Kostanay, three points) or the four existing Akmola landmarks. Expand the panel and enable **Pick on map**, remove or add markers (up to five), and press **Load route** to build the ordered path and prepare its track. Picking remains enabled after loading, so you can continue editing. Click a grid cell, or use Tab, arrow keys and Enter/Space. Use **+ / − / Fit map**, the mouse wheel or a two-finger pinch to zoom (100–800%), then drag to pan. Markers can be placed with consecutive clicks or taps. Water does not restrict selection or routing; no land/water mask is requested. Region boundaries and holes remain enforced. If a draft fails, the active route is retained. Changing date or source keeps the custom geometry and resets audio for explicit loading; changing region or choosing **Preset route** restores that region’s original 48/56 steps. No audio starts automatically. Changing the language or section preserves playback. NASA images are cached outside the project under the user's cache directory; an empty cache needs network access. See [the local demo guide](docs/LOCAL_DEMO.md) for saved-data mode, CSV contracts, language controls, audio export and tests.

## Data and attribution

The NOAA-20 data use [NASA Earthdata GIBS rolling 8-day NDVI](https://gibs.earthdata.nasa.gov/layer-metadata/v1.0/VIIRS_NOAA20_NDVI_8Day.json) and the [GIBS display legend](https://gibs.earthdata.nasa.gov/colormaps/v1.3/MODIS_NDVI.xml). The EIC loader uses native georeferenced frames and its own color scale from [NASA Scientific Visualization Studio / Earth Information Center: Near Real-Time NDVI](https://svs.gsfc.nasa.gov/5544/).

Map boundaries use [OpenStreetMap data under ODbL](https://www.openstreetmap.org/copyright); the original SVG and GeoJSON source information is in [MAP-SOURCES.md](data/maps/MAP-SOURCES.md).

CSV provenance, dates and source links supplied through Issues #1, #11 and #13 are recorded in [data/real-test](data/real-test/README.md). Synthetic data are explicitly labeled in the app.

This is an independent hackathon project, not an official NASA product.

## License

Original Steppe Jukebox contributions are licensed under the [MIT License](LICENSE). Third-party data, imagery, and other materials retain their own terms and attribution.
