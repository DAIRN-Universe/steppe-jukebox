# Steppe Jukebox

A DAIRN Great Steppe project for the [2026 NASA Space Apps Challenge: The Earth Information Jukebox](https://www.spaceappschallenge.org/2026/challenges/the-earth-information-jukebox/).

Steppe Jukebox lets people see and hear how vegetation varies along routes across Kazakhstan's Kostanay and Akmola regions. It loads NASA GIBS NOAA-20/VIIRS or NASA EIC Suomi NPP/VIIRS visualizations and turns vegetation-index color classes into notes while highlighting the corresponding cells on a map.

## First working version

- Compare spring and summer along the same route. Planned map landmarks include Kamennoye Lake, Naurzum, and Akkum in the Altyn Dala reserve.
- Use the same five-note scale, route, and tempo for both frames. Missing data are represented by silence.
- Show the original frame, date, and color legend. The notes represent color classes from the published visualization, not precise NDVI measurements.
- Run as a Python and Streamlit application with keyboard-accessible playback. Add autumn and winter after validating the first comparison.

## Status

Version **v0.4.0** is the first release that builds the map and sound from downloaded NASA data or the loader's verified disk cache. GIBS is the default source; EIC is selected separately. Choose an exact date, then press **Load**. Kostanay has 48 route positions and a 24-second track; Akmola has 56 positions and a 28-second track, using the same five notes and 120 BPM. Key places appear as **+**; the current cell and travelled path become visible during playback, while the upcoming route stays hidden.

Classes describe the selected product's color scale, not precise numerical NDVI. GIBS and EIC use their own scales, so class numbers need not match between sources. Journey mode uses the date of each step; unavailable EIC dates are reported without substitution. Location and date change together, so the journey does not establish a vegetation trend. In **v0.5.2**, the Minimal Instrument interface keeps the v0.4.2 NASA map and adds a current-point card, a seekable progress bar, and previous/next step buttons. Click or drag the progress bar, or use **←/→** to move by 0.5 seconds while preserving playback or pause. Selection fields and navigation tabs keep their native arrow-key behavior. Diagnostics, point tables, cache controls and optional layers are in a collapsed **Technical information** section. Playback controls sit above the map and settings, keeping them visible without scrolling in a 1280×720 window and at the effective viewports for 125%/150% zoom. Header spacing and side gutters are compact; phone screens remain free of horizontal scrolling. The Space Apps hackathon logo appears before DAIRN in the header. Listen to the steppe and How it works, visible keyboard focus, and Kazakh, English and Russian translations remain available. The released v0.3.0 CSV datasets remain unchanged and can be opened explicitly in saved-data mode.

The user confirmed the working interface. Targeted checks covered both sources, both regions, dates, keyboard playback, mobile layouts, three languages and offline replay from a prepared cache; the full suite was not rerun. EIC's first download retrieves a global frame and can take around two minutes on the tested connection. Arbitrary routes, a full online journey check and screen-reader evaluation remain separate work. See [the v0.5.2 release report](docs/RELEASE_0.5.2.md) for the compact layout and [the v0.5.0 report](docs/RELEASE_0.5.0.md) for playback acceptance results and remaining limits.

## Run the preview

Python 3.11 or newer:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Open `http://localhost:8501`. Select **Region**, **Data source** and an exact **Date**, press **Load route**, then start playback. For an initial comparison, use April 20 or June 10, 2026; both are in the checked EIC catalog. **Journey through time** loads the dates required by each step and reports missing frames. Changing the source, region, date or mode stops playback and resets highlighting without autoplay. Changing the language or section preserves playback. NASA images are cached outside the project under the user's cache directory; an empty cache needs network access. See [the local demo guide](docs/LOCAL_DEMO.md) for saved-data mode, CSV contracts, language controls, audio export and tests.

## Data and attribution

The NOAA-20 data use [NASA Earthdata GIBS rolling 8-day NDVI](https://gibs.earthdata.nasa.gov/layer-metadata/v1.0/VIIRS_NOAA20_NDVI_8Day.json) and the [GIBS display legend](https://gibs.earthdata.nasa.gov/colormaps/v1.3/MODIS_NDVI.xml). The EIC loader uses native georeferenced frames and its own color scale from [NASA Scientific Visualization Studio / Earth Information Center: Near Real-Time NDVI](https://svs.gsfc.nasa.gov/5544/).

Map boundaries use [OpenStreetMap data under ODbL](https://www.openstreetmap.org/copyright); the original SVG and GeoJSON source information is in [MAP-SOURCES.md](data/maps/MAP-SOURCES.md).

CSV provenance, dates and source links supplied through Issues #1, #11 and #13 are recorded in [data/real-test](data/real-test/README.md). Synthetic data are explicitly labeled in the app.

This is an independent hackathon project, not an official NASA product.

## License

Original Steppe Jukebox contributions are licensed under the [MIT License](LICENSE). Third-party data, imagery, and other materials retain their own terms and attribution.
