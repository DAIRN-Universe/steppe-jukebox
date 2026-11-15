/* One audio clock; language changes update text without touching the transport. */
(() => {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const audio = $("audio"), toggle = $("toggle"), select = $("season");
  const languageSelect = $("language");
  const modeSelect = $("mode"), regionSelect = $("region");
  const svgNS = "http://www.w3.org/2000/svg";
  const storageKey = "steppe-jukebox.language";
  const supported = ["kk", "en", "ru"];
  let data, season, revision, catalog;
  let view = "listen";
  let mode = "fixed";
  let language = "en", preference = "auto";
  let buttonState = "play", audioError = null;
  let generation = 0, started = false, wantsPlayback = false;
  let frame = null, activeIndex = -1;
  let rows = [], markers = [];
  let mapGeometry = null, renderedMapWidth = 0;
  let isLive = false, mapDate = null;
  const mapView = new window.MapViewport({enabled: () => isLive, geometry: () => mapGeometry,
    redraw: () => { if (season) drawRoute(); }});
  window.steppeMapView = mapView;
  const atEnd = () => started && season && audio.currentTime >= season.duration_s;
  function liveStep() { return atEnd() ? (season?.intervals.length || 1)-1 : Math.max(0, activeIndex); }
  const live = new window.LivePlayerSession({reset: resetTransport, selection: () => chooseMode(mode),
    prepare: () => activateTrack(live.placeholder(data, mode)),
    region: () => regionSelect.value || data.region_key, mode: () => mode, text: (...args) => t(...args),
    redraw: () => { if (season) drawRoute(); }, track: activateTrack, pause: () => { if (season) pause(); },
    restore: () => chooseRegion(regionSelect.value),
    geometry: definition => {
      data = {...data, route: definition.route, map_config: definition.map_config, journey: null,
        seasons: [{...data.seasons[0], duration_s: definition.route.length * data.step_seconds, intervals: definition.intervals}]};
    },
    currentDate: () => season?.intervals[liveStep()]?.date || live.day()});
  window.steppeLive = live;
  live.map.onFocusCell = cell => mapView.reveal(cell);
  try {
    const saved = localStorage.getItem(storageKey);
    if (["auto", ...supported].includes(saved)) preference = saved;
  } catch { /* Browser storage may be disabled; switching still works. */ }

  function systemLanguage() {
    for (const locale of [...(navigator.languages || []), navigator.language]) {
      const base = (locale || "").toLowerCase().split(/[-_]/)[0];
      if (supported.includes(base)) return base;
    }
    return "en";
  }

  function t(key, values = {}) {
    const template = data.translations[language][key] ?? data.translations.en[key];
    return template.replace(/\{(\w+)\}/g, (_, name) => String(values[name]));
  }

  const numberLocale = () => ({kk: "kk-KZ", en: "en-GB", ru: "ru-RU"}[language]);

  function seconds(value) {
    return value.toLocaleString(numberLocale(), {minimumFractionDigits: 1, maximumFractionDigits: 1});
  }

  const seasonName = () => data.translations[language][season.key] ?? season.name;
  const placeName = (slot) => slot.landmark ? (data.translations[language][slot.landmark] ?? slot.landmark) : t("route_point");
  const liveLandmarks = () => (data.journey?.intervals || []).flatMap((slot, index) => slot.landmark
    ? [{...data.route[index], index, name_key: slot.landmark}] : []);
  const regionKey = () => data.region_key || (data.route[0]?.cell_id.startsWith("KST-") ? "kostanay" : "custom_region");

  function updateViewLayout() {
    const hidden = view !== "listen" || Boolean(data.error);
    for (const id of ["listen-heading", "selection-panel", "route-context-card", "playback-controls"]) $(id).hidden = hidden;
    document.querySelector(".player-layout").classList.toggle("without-sidebar", hidden);
  }

  function showView(value, focus = false) {
    view = value;
    updateViewLayout();
    for (const key of ["listen", "method"]) {
      const tab = $(`tab-${key}`), selected = key === view;
      tab.setAttribute("aria-selected", String(selected));
      tab.tabIndex = selected ? 0 : -1;
      $(`${key}-view`).hidden = !selected;
    }
    if (focus) $(`tab-${view}`).focus();
    if (view === "listen" && season) drawRoute();
    resize();
  }

  function sourceLink(url, label) {
    const link = document.createElement("a");
    link.href = url;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.textContent = label;
    return link;
  }

  function renderContext() {
    const key = regionKey();
    $("region-heading").textContent = t(key);
    $("map-region").textContent = key === "custom_region" ? "" : t(key);
    $("route-summary").textContent = t("route_summary", {count: data.route.length, duration: seconds(season.duration_s), bpm: data.bpm});
    const landmarks = $("route-landmarks");
    landmarks.replaceChildren();
    for (const slot of data.journey?.intervals || []) {
      if (!slot.landmark) continue;
      const item = document.createElement("li");
      item.textContent = `${placeName(slot)} · ${slot.cell_id}`;
      landmarks.append(item);
    }
    const observation = $("observation-source");
    observation.textContent = mode === "journey" ? t("journey_summary", {start: season.intervals[0].date, end: season.intervals.at(-1).date, count: data.route.length}) : `${seasonName()} · ${season.date || t("no_date")}`;
    if (season.source_url) observation.append(document.createElement("br"), sourceLink(season.source_url, t("source_link")));
    $("map-attribution").hidden = !data.map_source_url;
    $("map-credit").hidden = !data.map_source_url;
    if (data.map_source_url) $("map-source").href = data.map_source_url;
  }

  function renderCurrentStep(index) {
    const slot = season.intervals[index], cell = data.route[index];
    const date = slot.date || season.date;
    $("step-date").textContent = date || t("no_date");
    if (date) $("step-date").setAttribute("datetime", date); else $("step-date").removeAttribute("datetime");
    const coordinate = (value) => value.toLocaleString(numberLocale(), {maximumFractionDigits: 4});
    $("step-place").textContent = t("step_coordinates", {place: placeName(slot), cell: slot.cell_id, lat: coordinate(cell.lat), lon: coordinate(cell.lon)});
    const distance = (value) => value.toLocaleString(numberLocale(), {minimumFractionDigits: 1, maximumFractionDigits: 1});
    $("step-position").hidden = !Number.isFinite(slot.distance_km) || !Number.isFinite(season.distance_km);
    if (!$("step-position").hidden) $("step-position").textContent = t("journey_position", {index: index + 1, total: rows.length, distance: distance(slot.distance_km), total_distance: distance(season.distance_km)});
  }

  function send(type, fields = {}) {
    window.parent.postMessage({isStreamlitMessage: true, type, ...fields}, "*");
  }

  function resize() {
    send("streamlit:setFrameHeight", {height: Math.ceil(document.documentElement.getBoundingClientRect().height)});
  }

  function setButton(state) {
    buttonState = state;
    toggle.dataset.state = state;
    toggle.textContent = t(state);
    toggle.setAttribute("aria-label", t(state));
  }

  function sizeMarker(marker, active) {
    const size = active && marker.classList.contains("compact") ? 14 : Number(marker.dataset.size);
    const rect = marker.querySelector("rect");
    for (const [key, value] of Object.entries({x: -size / 2, y: -size / 2, width: size, height: size, rx: Math.min(4, size / 4)})) {
      rect.setAttribute(key, value);
    }
  }

  function highlightMarker(index) {
    if (!markers[index]) return;
    markers[index].classList.add("active");
    sizeMarker(markers[index], true);
    $("map-content").append(markers[index]);
  }

  function setActive(index) {
    if (index === activeIndex) return;
    if (activeIndex >= 0) {
      rows[activeIndex]?.classList.remove("active");
      rows[activeIndex]?.removeAttribute("aria-current");
      markers[activeIndex]?.classList.remove("active");
      if (markers[activeIndex]) sizeMarker(markers[activeIndex], false);
    }
    activeIndex = index;
    if (index >= 0) {
      if (!rows[index]) return;
      rows[index].classList.add("active");
      rows[index].setAttribute("aria-current", "step");
      // SVG paints in DOM order: the current cell must stay above nearby cells.
      highlightMarker(index);
      const container = rows[index].closest(".table-scroll");
      const rowRect = rows[index].getBoundingClientRect();
      const containerRect = container.getBoundingClientRect();
      if (rowRect.top < containerRect.top || rowRect.bottom > containerRect.bottom) {
        container.scrollTop += rowRect.top - containerRect.top - (container.clientHeight - rowRect.height) / 2;
      }
    }
  }

  function renderPosition() {
    if (!season) return;
    const time = started ? Math.min(audio.currentTime || 0, season.duration_s) : 0;
    $("progress").value = time;
    $("progress").disabled = !season.audio_src || audio.readyState < 1 || Boolean(audioError) || (isLive && !live.ready);
    $("step-back").disabled = $("progress").disabled || time <= 0;
    $("step-forward").disabled = $("progress").disabled || time >= season.duration_s;
    $("progress").style.setProperty("--progress", `${time / season.duration_s * 100}%`);
    $("progress").setAttribute("aria-valuetext", t("clock", {current: seconds(time), duration: seconds(season.duration_s)}));
    $("clock").textContent = t("clock", {current: seconds(time), duration: seconds(season.duration_s)});
    // Half-open intervals come from the same sample offsets as the WAV.
    const ended = atEnd();
    const index = !started || ended ? -1 : season.intervals.findIndex((slot) => time >= slot.start_s && time < slot.end_s);
    setActive(index);
    if (isLive) {
      const day = season.intervals[liveStep()]?.date || live.day();
      if (mapDate !== day) drawRoute();
      live.map.highlight(index, ended);
    }
    const current = ended ? rows.length - 1 : Math.max(0, index);
    renderCurrentStep(current);
    renderPoint(current, index >= 0 || ended);
    let status = t(ended ? "ended" : "ready");
    if (!ended && index >= 0) {
      const slot = season.intervals[index];
      const note = slot.note ? t("class_note", {value: slot.ndvi_class, note: slot.note}) : t("missing_rest");
      status = t(mode === "journey" ? "journey_status" : "status_slot", {phase: t(audio.paused && !wantsPlayback ? "paused" : "playing"),
        cell: slot.cell_id, note, index: index + 1, total: rows.length, date: slot.date, place: mode === "journey" ? placeName(slot) : ""});
    }
    if ($("status").textContent !== status) $("status").textContent = status;
    if (isLive && !live.ready) $("status").textContent = $("load-state").textContent;
  }

  function renderPoint(index, positioned) {
    const slot = season.intervals[index];
    const ready = !isLive || live.ready;
    const missing = ready && positioned && !slot.note;
    $("point-count").textContent = positioned ? `${index + 1} / ${rows.length}` : String(rows.length);
    $("point-cell").textContent = ready && positioned ? slot.cell_id : t("route_positions");
    $("point-note").textContent = !ready ? "—" : !positioned ? "C D E G A" : slot.note || "∅";
    $("point-note-detail").textContent = !ready ? t("point_awaiting") : !positioned ? t("scale_intro") : missing ? t("missing_rest") : t("class_note", {value: slot.ndvi_class, note: slot.note});
    document.querySelector(".point-card").dataset.state = missing ? "missing" : "normal";
    document.querySelector(".point-card").dataset.positioned = String(positioned);
    for (const item of $("journey-progress").children) {
      const active = positioned && index >= Number(item.dataset.start) && index <= Number(item.dataset.end);
      item.classList.toggle("reached", positioned && index >= Number(item.dataset.start));
      if (active) item.setAttribute("aria-current", "step"); else item.removeAttribute("aria-current");
    }
  }

  function drawJourneyProgress() {
    const list = $("journey-progress");
    list.hidden = mode !== "journey";
    list.replaceChildren();
    if (mode !== "journey") return;
    const groups = Math.min(4, season.intervals.length);
    for (let group = 0; group < groups; group++) {
      const start = Math.floor(group * season.intervals.length / groups);
      const end = Math.floor((group + 1) * season.intervals.length / groups) - 1;
      const item = document.createElement("li"), date = document.createElement("time"), step = document.createElement("span");
      item.dataset.start = start; item.dataset.end = end;
      date.textContent = season.intervals[start].date; date.dateTime = season.intervals[start].date;
      step.textContent = `${start + 1} / ${season.intervals.length}`;
      item.append(date, step); list.append(item);
    }
  }

  function seek(value) {
    if (!season?.audio_src || $("progress").disabled) return;
    const time = Math.max(0, Math.min(season.duration_s, Number(value)));
    if (!Number.isFinite(time)) return;
    // The native media clock also drives the map, table, date and point card.
    // Seeking never calls play(): a paused or unstarted track stays silent.
    started = true;
    audio.currentTime = time;
    setButton(time >= season.duration_s ? "replay" : audio.paused && !wantsPlayback ? "resume" : "pause");
    renderPosition();
  }

  function seekStep(direction) {
    if (!season || $("progress").disabled) return;
    if (direction < 0 && audio.currentTime <= 0 || direction > 0 && atEnd()) return;
    seek(audio.currentTime + direction * data.step_seconds);
  }

  function animate() {
    renderPosition();
    frame = audio.paused || audio.ended ? null : requestAnimationFrame(animate);
  }

  function stopAnimation() {
    if (frame !== null) cancelAnimationFrame(frame);
    frame = null;
  }

  async function play() {
    const token = ++generation;
    if (audio.ended || audio.currentTime >= season.duration_s) audio.currentTime = 0;
    started = true;
    wantsPlayback = true;
    audioError = null;
    $("error").hidden = true;
    setButton("pause");
    try {
      await audio.play(); // Direct native button click, including Enter/Space.
      if (token !== generation) return;
      renderPosition();
    } catch {
      if (token !== generation) return;
      wantsPlayback = false;
      audio.pause();
      setButton("play");
      audioError = "play_error";
      refreshText();
    }
  }

  function pause() {
    generation++;
    wantsPlayback = false;
    audio.pause();
    stopAnimation();
    setButton("resume");
    renderPosition();
  }

  function svgElement(name, attributes) {
    const node = document.createElementNS(svgNS, name);
    for (const [key, value] of Object.entries(attributes)) node.setAttribute(key, value);
    return node;
  }

  function coordinateTicks(min, max, count) {
    const rawStep = (max - min) / Math.max(1, count - 1);
    const magnitude = 10 ** Math.floor(Math.log10(rawStep));
    let step = [1, 2, 5, 10].find((multiple) => multiple * magnitude >= rawStep) * magnitude;
    // A rounded step can leave only one tick in a narrow, offset range.
    while (Math.floor(max / step + 1e-9) - Math.ceil(min / step - 1e-9) + 1 < 2) step /= 2;
    let precision = Math.max(0, -Math.floor(Math.log10(step)));
    while (Math.abs(Number(step.toFixed(precision)) - step) > step * 1e-8) precision++;
    const first = Math.ceil(min / step - 1e-9) * step;
    const ticks = [];
    for (let index = 0; index < 50; index++) {
      const value = first + index * step;
      if (value > max + step * 1e-9) break;
      const coordinate = Math.abs(value) < step * 1e-8 ? 0 : Number(value.toFixed(precision));
      ticks.push({value: coordinate, label: `${coordinate.toLocaleString(numberLocale(), {
        minimumFractionDigits: precision, maximumFractionDigits: precision, useGrouping: false})}°`});
    }
    return ticks;
  }

  function renderAxes() {
    if (!mapGeometry) return;
    const {left, right, top, bottom, height, projectX, projectY, longitudeRange, latitudeRange} = mapGeometry;
    const axes = $("map-axes"), grid = $("map-grid");
    axes.replaceChildren();
    grid.replaceChildren();
    axes.append(svgElement("path", {d: `M ${left} ${top} V ${bottom} H ${right}`, class: "axis-line"}));
    const xTicks = coordinateTicks(...longitudeRange, Math.max(2, Math.min(6, Math.floor((right - left) / 90) + 1)));
    const yTicks = coordinateTicks(...latitudeRange, Math.max(2, Math.floor((bottom - top) / 50) + 1));
    for (const tick of xTicks) {
      const x = projectX(tick.value);
      grid.append(svgElement("line", {x1: x, y1: top, x2: x, y2: bottom, class: "grid-line"}));
      const group = svgElement("g", {class: "axis-tick", "data-axis": "longitude", "data-value": tick.value});
      const text = svgElement("text", {x, y: bottom + 24, "text-anchor": "middle"});
      text.textContent = tick.label;
      group.append(svgElement("line", {x1: x, y1: bottom, x2: x, y2: bottom + 6, class: "axis-line"}), text);
      axes.append(group);
    }
    for (const tick of yTicks) {
      const y = projectY(tick.value);
      grid.append(svgElement("line", {x1: left, y1: y, x2: right, y2: y, class: "grid-line"}));
      const group = svgElement("g", {class: "axis-tick", "data-axis": "latitude", "data-value": tick.value});
      const text = svgElement("text", {x: left - 10, y, "text-anchor": "end", "dominant-baseline": "central"});
      text.textContent = tick.label;
      group.append(svgElement("line", {x1: left - 6, y1: y, x2: left, y2: y, class: "axis-line"}), text);
      axes.append(group);
    }
    $("longitude-label").setAttribute("x", (left + right) / 2);
    $("longitude-label").setAttribute("y", height - 12);
    $("longitude-label").textContent = t("longitude_axis");
    $("latitude-label").setAttribute("transform", `translate(24,${(top + bottom) / 2}) rotate(-90)`);
    $("latitude-label").textContent = t("latitude_axis");
  }

  function drawRoute() {
    const map = $("route-map");
    const viewWidth = Math.max(280, map.clientWidth || renderedMapWidth || 720), viewHeight = map.clientHeight || 430;
    renderedMapWidth = map.clientWidth;
    map.setAttribute("viewBox", `0 0 ${viewWidth} ${viewHeight}`);
    const left = 100, right = viewWidth - 22, top = 22, bottom = viewHeight - 66;
    const content = $("map-content");
    content.replaceChildren();
    const lats = data.route.map((cell) => cell.lat), lons = data.route.map((cell) => cell.lon);
    const polygons = data.boundary?.type === "Polygon" ? [data.boundary.coordinates] : data.boundary?.coordinates || [];
    const boundaryPoints = polygons.flat(2);
    const minLat = Math.min(...lats, ...boundaryPoints.map((point) => point[1])), maxLat = Math.max(...lats, ...boundaryPoints.map((point) => point[1]));
    const minLon = Math.min(...lons, ...boundaryPoints.map((point) => point[0])), maxLon = Math.max(...lons, ...boundaryPoints.map((point) => point[0]));
    const cosLat = Math.max(0.01, Math.cos((isLive ? minLat + maxLat : Math.min(...lats) + Math.max(...lats)) / 2 * Math.PI / 180));
    // Minimum extent provides context for a single point or a flat route.
    const width = Math.max(maxLon - minLon, 0.02) * cosLat, height = Math.max(maxLat - minLat, 0.02);
    const scale = Math.min((right - left - 40) / width, (bottom - top - 40) / height) * (isLive ? mapView.zoom : 1);
    const centerX = (left + right) / 2, centerY = (top + bottom) / 2;
    const baseLon = (minLon + maxLon) / 2, baseLat = (minLat + maxLat) / 2;
    const centerLon = Math.max(minLon, Math.min(maxLon, baseLon + (isLive ? mapView.lon : 0)));
    const centerLat = Math.max(minLat, Math.min(maxLat, baseLat + (isLive ? mapView.lat : 0)));
    if (isLive) { mapView.lon = centerLon - baseLon; mapView.lat = centerLat - baseLat; }
    const projectX = (lon) => centerX + (lon - centerLon) * cosLat * scale;
    const projectY = (lat) => centerY - (lat - centerLat) * scale;
    mapGeometry = {left, right, top, bottom, height: viewHeight, projectX, projectY, centerX, centerY, centerLon, centerLat, cosLat, scale,
      longitudeRange: [Math.max(-180, centerLon + (left - centerX) / (cosLat * scale)), Math.min(180, centerLon + (right - centerX) / (cosLat * scale))],
      latitudeRange: [Math.max(-90, centerLat - (bottom - centerY) / scale), Math.min(90, centerLat - (top - centerY) / scale)]};
    for (const id of ['map-boundary', 'map-grid', 'map-content']) {
      if (isLive) $(id).setAttribute('clip-path', 'url(#map-viewport-clip)');
      else $(id).removeAttribute('clip-path');
    }
    for (const [key, value] of Object.entries({x: left, y: top, width: right-left, height: bottom-top})) $('map-viewport-rect').setAttribute(key, value);
    mapView.refresh();
    renderAxes();
    $("map-boundary").replaceChildren();
    for (const polygon of polygons) {
      const path = polygon.map((ring) => "M " + ring.map(([lon, lat]) => `${projectX(lon)},${projectY(lat)}`).join(" L ") + " Z").join(" ");
      $("map-boundary").append(svgElement("path", {d: path, class: "region-outline"}));
    }
    if (isLive) {
      mapDate = season?.intervals[liveStep()]?.date || live.day();
      live.map.draw(data.map_config, live.slice(mapDate), mapGeometry, activeIndex, atEnd());
      live.decorateMap();
      live.refresh();
      markers = [];
      return;
    }
    const points = data.route.map((cell) => [projectX(cell.lon), projectY(cell.lat)]);
    content.append(svgElement("polyline", {points: points.map((point) => point.join(",")).join(" "), class: "route-line"}));
    const spacing = points.slice(1).map(([x, y], i) => Math.hypot(x - points[i][0], y - points[i][1])).filter((distance) => distance > 0);
    const markerSize = Math.min(26, Math.max(1.25, Math.min(...spacing) * 0.8));
    const compact = markerSize < 18;
    markers = points.map(([x, y], index) => {
      const slot = season.intervals[index];
      const color = slot.ndvi_class ? data.scale[slot.ndvi_class - 1].color : data.missing_color;
      const group = svgElement("g", {class: compact ? "cell compact" : "cell", "data-cell-id": slot.cell_id,
        "data-size": markerSize, transform: `translate(${x},${y})`});
      const text = svgElement("text", {x: compact ? 16 : 0, y: 0});
      text.textContent = index + 1;
      const rect = svgElement("rect", {fill: color});
      rect.style.setProperty("--cell-stroke", compact ? 0.3 : 2);
      const title = svgElement("title", {});
      title.textContent = `${slot.cell_id}${slot.date ? ` · ${slot.date} · ${placeName(slot)}` : ""}: ${slot.note || t("missing_rest")}`;
      group.append(title, rect, text);
      sizeMarker(group, false);
      content.append(group);
      return group;
    });
    highlightMarker(activeIndex);
  }

  function drawTable() {
    const body = $("timeline").querySelector("tbody");
    body.replaceChildren();
    rows = season.intervals.map((slot) => {
      const row = document.createElement("tr");
      row.dataset.cellId = slot.cell_id;
      for (let i = 0; i < (mode === "journey" ? 6 : 5); i++) row.append(document.createElement("td"));
      body.append(row);
      return row;
    });
    $("timeline").closest(".table-scroll").scrollTop = 0;
  }

  function refreshText() {
    if (!data) return;
    document.documentElement.lang = language;
    document.title = t("page_title");
    document.querySelectorAll("[data-i18n]").forEach((node) => { node.textContent = t(node.dataset.i18n); });
    document.querySelectorAll("[data-i18n-aria]").forEach((node) => { node.setAttribute("aria-label", t(node.dataset.i18nAria)); });
    document.querySelectorAll("[data-i18n-title]").forEach((node) => { node.title = t(node.dataset.i18nTitle); });
    $("system-language").textContent = t("system_language");
    languageSelect.value = preference;
    $("test-warning").hidden = Boolean(data.error) || !data.is_test;
    $("description").textContent = data.description_i18n?.[language] || data.description || "";
    $("description").hidden = Boolean(data.error) || !$("description").textContent;
    $("data-error").hidden = !data.error;
    $("footer").hidden = Boolean(data.error);
    if (data.error) {
      $("data-error").textContent = t("data_error", {detail: t(`error_${data.error.code}`, data.error.context)});
      resize();
      return;
    }
    if (!season) return;
    for (const option of regionSelect.options) option.textContent = t(option.value);
    $("season-field").hidden = mode === "journey";
    $("journey-caveat").hidden = mode !== "journey";
    $("current-step").hidden = false;
    $("date-column").hidden = mode !== "journey";
    $("audio").setAttribute("aria-label", t(mode === "journey" ? "journey_audio_label" : "audio_label"));
    renderAxes();
    for (const option of select.options) option.textContent = t(option.value);
    setButton(buttonState);
    $("tempo").textContent = t("tempo", {bpm: data.bpm, step: seconds(data.step_seconds)});
    const info = $("season-info");
    info.textContent = mode === "journey" ? t("journey_summary", {start: season.intervals[0].date, end: season.intervals.at(-1).date, count: rows.length}) + " · " : `${seasonName()} · ${season.date || t("no_date")} · `;
    if (season.source_url) {
      const link = document.createElement("a");
      link.href = season.source_url;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.textContent = t("source_link");
      info.append(link);
    } else info.append(document.createTextNode(t(data.is_test ? "test_sequence" : "source_missing")));
    $("timeline-caption").textContent = t("timeline_caption", {season: seasonName()});
    season.intervals.forEach((slot, index) => {
      const values = [index + 1, slot.cell_id, slot.ndvi_class ?? t("missing"), slot.note || t("rest"), `${seconds(slot.start_s)}–${seconds(slot.end_s)}`];
      if (mode === "journey") values.splice(2, 0, slot.date);
      [...rows[index].children].forEach((td, i) => { td.textContent = values[i]; });
      if (markers[index]) markers[index].querySelector("title").textContent = `${slot.cell_id}${slot.date ? ` · ${slot.date} · ${placeName(slot)}` : ""}: ${slot.note || t("missing_rest")}`;
    });
    const noteNames = data.translations[language].note_names;
    const notes = data.scale.map((note, index) => t("scale_note", {value: index + 1, label: noteNames[index], note: note.name})).join(", ");
    $("scale-description").textContent = t("scale_description", {notes});
    $("legend").replaceChildren();
    $("method-scale").replaceChildren();
    [...data.scale.map((note, i) => ({color: note.color, text: `${i + 1} → ${note.name} (${noteNames[i]})`})),
      {color: data.missing_color, text: t("missing_rest")}].forEach(({color, text}) => {
      const item = document.createElement("li"), swatch = document.createElement("span");
      swatch.className = "swatch";
      swatch.style.backgroundColor = color;
      swatch.setAttribute("aria-hidden", "true");
      item.append(swatch, document.createTextNode(text));
      $("legend").append(item);
    });
    data.scale.forEach((note, index) => {
      const item = document.createElement("li"), swatch = document.createElement("span"), name = document.createElement("strong"), label = document.createElement("span");
      swatch.className = "swatch"; swatch.style.backgroundColor = note.color;
      swatch.setAttribute("aria-hidden", "true");
      name.textContent = note.name; label.textContent = t("scale_note", {value: index + 1, label: noteNames[index], note: note.name});
      item.append(swatch, name, label); $("method-scale").append(item);
    });
    $("error").hidden = !audioError;
    if (audioError) $("error").textContent = t(audioError);
    renderContext();
    renderPosition();
    if (isLive) {
      $("load-state").hidden = false; $("live-diagnostics").hidden = false; $("provider-method").hidden = false;
      $("interface").setAttribute("aria-label", t("live_interface"));
      $("audio").setAttribute("aria-label", t("live_audio"));
      $("keyboard-help").textContent = t("live_keyboard");
      document.querySelector('[data-i18n="route_hint"]').textContent = t("live_route_hint");
      live.decorateMap();
      $("journey-caveat").textContent = t("live_journey_caveat");
      live.refresh();
    }
    resize();
  }

  function chooseLanguage(choice, persist = true) {
    preference = choice;
    language = preference === "auto" ? systemLanguage() : preference;
    if (persist) {
      try { localStorage.setItem(storageKey, preference); } catch { /* Optional storage. */ }
    }
    // No source reload, play/pause call, or replacement of active rows/markers.
    refreshText();
  }

  function resetTransport() {
    generation++;
    wantsPlayback = false;
    started = false;
    audio.pause();
    stopAnimation();
    setActive(-1);
    audio.removeAttribute("src");
    audio.load();
    season = null;
    rows = [];
    markers = [];
    buttonState = "play";
    audioError = null;
  }

  function activateTrack(track) {
    resetTransport(); // Synchronous: old audio stops before loading the new source.
    season = track;
    if (mode === "fixed") select.value = season.key;
    if (season.audio_src) audio.src = season.audio_src;
    audio.load();
    $("progress").max = season.duration_s;
    drawRoute();
    drawTable();
    drawJourneyProgress();
    refreshText();
  }

  function chooseSeason(key) {
    activateTrack(data.seasons.find((item) => item.key === key));
  }

  function chooseMode(value) {
    mode = !isLive && value === "journey" && data.journey ? "journey" : "fixed";
    modeSelect.value = mode;
    if (isLive) {
      live.invalidate();
      return;
    }
    activateTrack(mode === "journey" ? data.journey : data.seasons.find((item) => item.key === select.value) ?? data.seasons[0]);
  }

  function chooseRegion(key) {
    const item = catalog.regions.find((region) => region.region_key === key);
    const selectedSeason = select.value;
    resetTransport();
    mapView.reset(false);
    data = {...item, translations: catalog.translations};
    if (isLive) live.resetRegion(data.map_config, liveLandmarks());
    regionSelect.value = key;
    select.replaceChildren();
    for (const track of data.seasons) {
      const option = document.createElement("option");
      option.value = track.key;
      select.append(option);
    }
    if (data.seasons.some((track) => track.key === selectedSeason)) select.value = selectedSeason;
    $("mode-field").hidden = isLive || !data.journey;
    chooseMode(mode);
    showView(view);
  }

  function render(payload, bootstrap = false) {
    if (payload.live && !bootstrap) {
      isLive = true; document.body.classList.add("live-mode");
      if (!catalog?.live) render(payload.base, true);
      live.cache = payload.cache; live.accept(payload);
      return;
    }
    if (payload.revision === revision) return;
    revision = payload.revision;
    $("app-version").textContent = payload.version ? `v${payload.version}` : "";
    data = payload;
    catalog = payload;
    language = preference === "auto" ? systemLanguage() : preference;
    $("interface").hidden = false;
    $("player").hidden = Boolean(data.error);
    updateViewLayout();
    $("navigation").hidden = Boolean(data.error);
    $("region-field").hidden = Boolean(data.error) || !payload.regions;
    if (data.error) {
      resetTransport();
      refreshText();
      return;
    }
    if (payload.regions) {
      regionSelect.replaceChildren();
      for (const item of payload.regions) {
        const option = document.createElement("option");
        option.value = item.region_key;
        regionSelect.append(option);
      }
      chooseRegion(payload.regions[0].region_key);
      return;
    }
    select.replaceChildren();
    for (const item of data.seasons) {
      const option = document.createElement("option");
      option.value = item.key;
      select.append(option);
    }
    $("mode-field").hidden = !data.journey;
    chooseMode("fixed");
  }

  toggle.addEventListener("click", () => wantsPlayback || !audio.paused ? pause() : play());
  select.addEventListener("change", () => chooseSeason(select.value));
  modeSelect.addEventListener("change", () => chooseMode(modeSelect.value));
  regionSelect.addEventListener("change", () => chooseRegion(regionSelect.value));
  $("restart").addEventListener("click", () => activateTrack(season));
  $("step-back").addEventListener("click", () => seekStep(-1));
  $("step-forward").addEventListener("click", () => seekStep(1));
  $("progress").addEventListener("input", (event) => seek(event.target.value));
  $("progress").addEventListener("keydown", (event) => {
    const direction = {ArrowRight: 1, ArrowUp: 1, ArrowLeft: -1, ArrowDown: -1}[event.key];
    if (!direction || $("progress").disabled) return;
    event.preventDefault();
    seekStep(direction);
  });
  document.addEventListener("keydown", (event) => {
    if (event.defaultPrevented || view !== "listen" || !season || $("progress").disabled || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
    const direction = {ArrowLeft: -1, ArrowRight: 1}[event.key];
    // Keep native arrows in form fields, tab navigation and technical tables.
    if (!direction || event.target.closest('input, select, textarea, [contenteditable], #navigation, #technical-details')) return;
    event.preventDefault();
    seekStep(direction);
  });
  document.querySelectorAll("[data-open-view], [data-view]").forEach((button) => {
    button.addEventListener("click", (event) => { event.preventDefault(); showView(button.dataset.openView || button.dataset.view, true); });
  });
  $("navigation").addEventListener("keydown", (event) => {
    const tabs = [...$("navigation").querySelectorAll("[role=tab]")];
    let index = tabs.indexOf(document.activeElement);
    if (index < 0 || !["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    index = event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1 : (index + (event.key === "ArrowRight" ? 1 : -1) + tabs.length) % tabs.length;
    showView(tabs[index].dataset.view, true);
  });
  languageSelect.addEventListener("change", () => chooseLanguage(languageSelect.value));
  window.addEventListener("languagechange", () => {
    if (preference === "auto") chooseLanguage("auto", false);
  });
  audio.addEventListener("playing", () => {
    stopAnimation();
    frame = requestAnimationFrame(animate);
  });
  audio.addEventListener("timeupdate", renderPosition);
  audio.addEventListener("loadedmetadata", renderPosition);
  audio.addEventListener("seeked", renderPosition);
  audio.addEventListener("pause", renderPosition);
  audio.addEventListener("ended", () => {
    if (!audio.ended) return; // Ignore an old track's queued event after a switch.
    wantsPlayback = false;
    stopAnimation();
    setButton("replay");
    renderPosition();
  });
  audio.addEventListener("error", () => {
    if (!audio.getAttribute("src") || !audio.error) return;
    generation++;
    wantsPlayback = false;
    stopAnimation();
    setButton("play");
    audioError = "load_error";
    refreshText();
  });
  window.addEventListener("pagehide", () => { generation++; audio.pause(); stopAnimation(); });
  window.addEventListener("message", (event) => {
    if (event.source === window.parent && event.data?.type === "streamlit:render" && event.data.args?.payload) render(event.data.args.payload);
  });
  new ResizeObserver(resize).observe(document.body);
  new ResizeObserver(() => {
    if (season && $("route-map").clientWidth !== renderedMapWidth) drawRoute();
  }).observe($("route-map"));
  send("streamlit:componentReady", {apiVersion: 1});
})();
