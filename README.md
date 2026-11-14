# Steppe Jukebox

A DAIRN Great Steppe project for the [2026 NASA Space Apps Challenge: The Earth Information Jukebox](https://www.spaceappschallenge.org/2026/challenges/the-earth-information-jukebox/).

Steppe Jukebox lets people see and hear how vegetation varies along a route across Kazakhstan's Kostanay Region. It turns vegetation-index color classes in NASA Earth Information Center imagery into notes while highlighting the corresponding cells on a map.

## First working version

- Compare spring and summer along the same route. Planned map landmarks include Kamennoye Lake, Naurzum, and Akkum in the Altyn Dala reserve.
- Use the same five-note scale, route, and tempo for both frames. Missing data are represented by silence.
- Show the original frame, date, and color legend. The notes represent color classes from the published visualization, not precise NDVI measurements.
- Run as a Python and Streamlit application with keyboard-accessible playback. Add autumn and winter after validating the first comparison.

## Status

The application supports two modes: a fixed date along the whole route, and a journey where both location and date change at every step. The default NOAA-20/VIIRS dataset has 48 route points. Its journey runs from April 15 to November 13, 2026 in 24 seconds, using the same five-note scale and 120 BPM as the fixed seasonal tracks.

The supplied real-data CSVs contain visualization classes, not raw numerical NDVI. The journey uses rolling 8-day composites and does not establish a vegetation trend: location and date change together. Streamlit provides keyboard playback, synchronized highlighting and dates, geographic axes, and Kazakh, English, and Russian interfaces. The original synthetic dataset and the separate EIC dataset remain available.

The user confirmed the Kostanay manual playback scenario before releasing v0.2.0. Akmola support is deferred. Source-image crops, independent verification of the supplied classes, and screen-reader evaluation remain separate acceptance work. See [the v0.2.0 release report](docs/RELEASE_0.2.0.md) for verified behavior and open checks.

## Run the preview

Python 3.11 or newer:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Open `http://localhost:8501`. Choose **Mode → Journey through time** for the dated journey, or **One date along the route** to compare Spring and Summer. Switching modes stops playback and resets highlighting. See [the local demo guide](docs/LOCAL_DEMO.md) for the CSV contracts, alternative datasets, language controls, audio export, and tests.

## Data and attribution

The NOAA-20 data use [NASA Earthdata GIBS rolling 8-day NDVI](https://gibs.earthdata.nasa.gov/layer-metadata/v1.0/VIIRS_NOAA20_NDVI_8Day.json) and the [GIBS display legend](https://gibs.earthdata.nasa.gov/colormaps/v1.3/MODIS_NDVI.xml). The separate EIC dataset refers to [NASA Scientific Visualization Studio / Earth Information Center: Near Real-Time NDVI](https://svs.gsfc.nasa.gov/5544/).

CSV provenance, dates and source links supplied through Issues #1 and #11 are recorded in [data/real-test](data/real-test/README.md). Synthetic data are explicitly labeled in the app.

This is an independent hackathon project, not an official NASA product.

## License

Original Steppe Jukebox contributions are licensed under the [MIT License](LICENSE). Third-party data, imagery, and other materials retain their own terms and attribution.
