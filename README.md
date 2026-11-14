# Steppe Jukebox

A DAIRN Great Steppe project for the [2026 NASA Space Apps Challenge: The Earth Information Jukebox](https://www.spaceappschallenge.org/2026/challenges/the-earth-information-jukebox/).

Steppe Jukebox lets people see and hear how vegetation varies along a route across Kazakhstan's Kostanay Region. It turns vegetation-index color classes in NASA Earth Information Center imagery into notes while highlighting the corresponding cells on a map.

## First working version

- Compare spring and summer along the same route. Planned map landmarks include Kamennoye Lake, Naurzum, and Akkum in the Altyn Dala reserve.
- Use the same five-note scale, route, and tempo for both frames. Missing data are represented by silence.
- Show the original frame, date, and color legend. The notes represent color classes from the published visualization, not precise NDVI measurements.
- Run as a Python and Streamlit application with keyboard-accessible playback. Add autumn and winter after validating the first comparison.

## Status

The source and implementation plan are identified. This repository starts with documentation only; the runnable application and validation on real frames are not yet available.

## Data and attribution

[NASA Scientific Visualization Studio / Earth Information Center: Near Real-Time Normalized Difference Vegetation Index (NDVI)](https://svs.gsfc.nasa.gov/5544/). Exact frame dates, source links, and any additional credits will be documented when the frames are selected.

This is an independent hackathon project, not an official NASA product.

## License

Original Steppe Jukebox contributions are licensed under the [MIT License](LICENSE). Third-party data, imagery, and other materials retain their own terms and attribution.
