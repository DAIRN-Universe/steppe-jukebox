"""Reproduce the Kostanay MOD13Q1 pilot from the NASA AppEEARS point export."""
import csv
import json
import math
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from PIL import Image, ImageDraw
from steppe_jukebox.data import load_route
from steppe_jukebox.sound import SCALE, MISSING_COLOR, build_track

DATA = ROOT / 'data/modis-pilot'
PREFIX = 'MOD13Q1_061__250m_16_days_'
YEARS = (2001, 2013, 2025)

def pixel(lat, lon):
    radius = 6371007.181
    tile = 2 * math.pi * radius / 36
    x = radius * math.radians(lon) * math.cos(math.radians(lat))
    y = radius * math.radians(lat)
    xx, yy = x + 18 * tile, 9 * tile - y
    h, v = math.floor(xx / tile), math.floor(yy / tile)
    return f'h{h:02}v{v:02}', math.floor((yy / tile - v) * 4800), math.floor((xx / tile - h) * 4800)

def validate_sample_location(sample, cell):
    try:
        coordinates = (float(sample['Latitude']), float(sample['Longitude']))
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f'Invalid sample coordinates for {cell.cell_id}') from exc
    if coordinates != (cell.lat, cell.lon):
        raise ValueError(f'Sample coordinates do not match route for {cell.cell_id}')
    actual = (sample['MODIS_Tile'], int(float(sample['MOD13Q1_061_Line_Y_250m'])), int(float(sample['MOD13Q1_061_Sample_X_250m'])))
    if pixel(cell.lat, cell.lon) != actual:
        raise ValueError(f'Geolocation mismatch: {cell.cell_id}, {actual}, {pixel(cell.lat, cell.lon)}')
    return actual

def classify(value, reliability, qa):
    if value is None or not -0.2 <= value <= 1 or reliability != 0 or qa is None or qa == 65535 or qa & 3:
        return None
    return min(5, max(1, math.floor(value * 5) + 1))

def colors():
    result = []
    entries = list(ET.parse(ROOT / 'data/nasa-palettes/ndvi.xml').iter('ColorMapEntry'))
    for target in (.1, .3, .5, .7, .9):
        for e in entries:
            value = e.get('value', '')
            try:
                low, high = map(float, value.strip('[]()').split(','))
            except ValueError:
                continue
            if e.get('transparent') != 'true' and low <= target < high:
                result.append('#' + ''.join(f'{int(x):02x}' for x in e.attrib['rgb'].split(',')))
                break
        else:
            raise ValueError(f'No NASA palette color for {target}')
    return result

def render_map(rows, year, palette, path):
    image = Image.new('RGB', (900, 800), 'white')
    draw = ImageDraw.Draw(image)
    west, east, south, north = 61, 67, 48, 55
    def xy(lon, lat): return (90 + (lon-west)/(east-west)*690, 70 + (north-lat)/(north-south)*650)
    geo = json.loads((ROOT / 'data/maps/kostanay.geojson').read_text())
    geometry = geo.get('geometry', geo)
    if geometry.get('type') == 'FeatureCollection': geometry = geometry['features'][0]['geometry']
    polys = [geometry['coordinates']] if geometry['type'] == 'Polygon' else geometry['coordinates']
    for poly in polys:
        for ring in poly: draw.line([xy(*p[:2]) for p in ring], fill='#99a3ad', width=2)
    points = [xy(float(r['lon']), float(r['lat'])) for r in rows]
    draw.line(points, fill='#34495e', width=2)
    for i, (row, (x,y)) in enumerate(zip(rows, points), 1):
        color = palette[int(row['class'])-1] if row['class'] else MISSING_COLOR
        draw.ellipse((x-6,y-6,x+6,y+6), fill=color, outline='black', width=1)
        if i in (1, 24, 48): draw.text((x+8,y-8), str(i), fill='black')
    draw.text((30, 20), f'MOD13Q1.061 | {year}-07-12 to {year}-07-27 | 48 route steps', fill='black')
    for i, c in enumerate(palette + [MISSING_COLOR]):
        x = 80 + i * 130
        draw.rectangle((x,750,x+20,770), fill=c, outline='black')
        draw.text((x+25,752), f'Class {i+1}' if i < 5 else 'Missing', fill='black')
    image.save(path)

def main():
    route = load_route(ROOT / 'data/real-test/noaa20-kostanay/route.csv')
    palette = colors()
    with (DATA / 'steppe-jukebox-mod13q1-pilot-MOD13Q1-061-results.csv').open() as f:
        source = list(csv.DictReader(f))
    index = {(r['ID'], r['Date']): r for r in source}
    if len(index) != 144 or len(source) != 144: raise ValueError('Expected exactly 144 distinct samples')
    summaries = {}
    for year in YEARS:
        rows, classes = [], []
        for cell in route:
            s = index[(cell.cell_id, f'{year}-07-12')]
            actual = validate_sample_location(s, cell)
            def number(name):
                raw = s[PREFIX + name]
                return float(raw) if raw.strip() else None
            value, qa, rel = number('NDVI'), number('VI_Quality'), number('pixel_reliability')
            qa = int(qa) if qa is not None else None
            rel = int(rel) if rel is not None else None
            cl = classify(value, rel, qa)
            classes.append(cl)
            rows.append({'cell_id': cell.cell_id, 'lat': cell.lat, 'lon': cell.lon, 'tile': actual[0], 'line': actual[1], 'sample': actual[2], 'ndvi': value, 'qa': qa, 'pixel_reliability': rel, 'class': cl or '', 'color': palette[cl-1] if cl else MISSING_COLOR, 'note': SCALE[cl-1].name if cl else '', 'status': 'valid' if cl else 'missing_or_unreliable'})
        with (DATA / f'{year}-route.csv').open('w', newline='') as f:
            w = csv.DictWriter(f, fieldnames=rows[0].keys(), lineterminator='\n'); w.writeheader(); w.writerows(rows)
        (DATA / f'{year}-route.wav').write_bytes(build_track(route, tuple(classes)).wav)
        render_map(rows, year, palette, DATA / f'{year}-route.png')
        summaries[year] = dict(Counter(str(c) if c is not None else 'missing' for c in classes))
    print('NASA palette:', palette)
    print('Counts:', json.dumps(summaries, sort_keys=True))

if __name__ == '__main__': main()
