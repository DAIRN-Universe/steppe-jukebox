# Steppe Jukebox

A DAIRN Great Steppe project for the [2026 NASA Space Apps Challenge: The Earth Information Jukebox](https://www.spaceappschallenge.org/2026/challenges/the-earth-information-jukebox/).

Steppe Jukebox lets people see and hear how vegetation varies along routes across Kazakhstan's Kostanay and Akmola regions. It turns vegetation-index color classes in NASA GIBS NOAA-20/VIIRS visualizations into notes while highlighting the corresponding cells on a map.

## First working version

- Compare spring and summer along the same route. Planned map landmarks include Kamennoye Lake, Naurzum, and Akkum in the Altyn Dala reserve.
- Use the same five-note scale, route, and tempo for both frames. Missing data are represented by silence.
- Show the original frame, date, and color legend. The notes represent color classes from the published visualization, not precise NDVI measurements.
- Run as a Python and Streamlit application with keyboard-accessible playback. Add autumn and winter after validating the first comparison.

## Status

Version **v0.3.0** supports Kostanay and Akmola, each with fixed spring/summer observations and a journey where location and date change at every step. Kostanay has 48 route positions and a 24-second track; Akmola has 56 positions and a 28-second track. Both journeys run from April 15 to November 13, 2026 on the same five-note scale and at 120 BPM. Kostanay is selected first.

The supplied real-data CSVs contain visualization classes, not raw numerical NDVI. The journey uses rolling 8-day composites and does not establish a vegetation trend: location and date change together. The responsive interface has Listen to the steppe, Plants and places, and How it works sections. It provides keyboard playback, synchronized highlighting and dates, geographic axes over OpenStreetMap region boundaries, and Kazakh, English, and Russian interfaces. The original synthetic dataset and the separate EIC dataset remain available.

The user confirmed the manual application check; 153 automated checks passed. Additional botanical data and sources are planned for later versions. Source-image crops, independent verification of the supplied classes, and screen-reader evaluation remain separate acceptance work. See [the v0.3.0 release report](docs/RELEASE_0.3.0.md) for verified behavior and open checks.

## Run the preview

Python 3.11 or newer:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Open `http://localhost:8501`. Select **Region** to choose Kostanay or Akmola. Choose **Mode → Journey through time** for the dated journey, or **One date along the route** to compare Spring and Summer. Changing the region, season, or mode stops playback and resets highlighting without autoplay. Changing the language or section preserves playback. See [the local demo guide](docs/LOCAL_DEMO.md) for the CSV contracts, alternative datasets, language controls, audio export, and tests.

## Data and attribution

The NOAA-20 data use [NASA Earthdata GIBS rolling 8-day NDVI](https://gibs.earthdata.nasa.gov/layer-metadata/v1.0/VIIRS_NOAA20_NDVI_8Day.json) and the [GIBS display legend](https://gibs.earthdata.nasa.gov/colormaps/v1.3/MODIS_NDVI.xml). The separate EIC dataset refers to [NASA Scientific Visualization Studio / Earth Information Center: Near Real-Time NDVI](https://svs.gsfc.nasa.gov/5544/).

Map boundaries use [OpenStreetMap data under ODbL](https://www.openstreetmap.org/copyright); the original SVG and GeoJSON source information is in [MAP-SOURCES.md](data/maps/MAP-SOURCES.md).

CSV provenance, dates and source links supplied through Issues #1, #11 and #13 are recorded in [data/real-test](data/real-test/README.md). Synthetic data are explicitly labeled in the app.

This is an independent hackathon project, not an official NASA product.

## License

Original Steppe Jukebox contributions are licensed under the [MIT License](LICENSE). Third-party data, imagery, and other materials retain their own terms and attribution.
