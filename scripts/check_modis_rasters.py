"""Compare independent NASA AppEEARS native GeoTIFF extracts to point samples."""
import csv
import math
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data/modis-pilot'
TIFS = DATA / 'raster-check'
PREFIX = 'MOD13Q1_061__250m_16_days_'

def read_at(path, latitude, longitude):
    radius = 6371007.181
    x = radius * math.radians(longitude) * math.cos(math.radians(latitude))
    y = radius * math.radians(latitude)
    with Image.open(path) as image:
        scale, tie = image.tag_v2[33550], image.tag_v2[33922]
        col = math.floor((x - tie[3]) / scale[0] + tie[0])
        row = math.floor((tie[4] - y) / scale[1] + tie[1])
        if not (0 <= col < image.width and 0 <= row < image.height): return None
        return image.getpixel((col, row)), row, col

def main():
    with (DATA / 'steppe-jukebox-mod13q1-pilot-MOD13Q1-061-results.csv').open() as source:
        samples = [row for row in csv.DictReader(source) if row['ID'] in ('KST-001', 'KST-024', 'KST-048')]
    files = list(TIFS.glob('*.tif'))
    checked = []
    for sample in samples:
        year = sample['Date'][:4]
        for layer in ('NDVI', 'VI_Quality', 'pixel_reliability'):
            matching = [f for f in files if f'__250m_16_days_{layer}_doy{year}193' in f.name]
            values = [(f, read_at(f, float(sample['Latitude']), float(sample['Longitude']))) for f in matching]
            values = [(f, result) for f, result in values if result is not None]
            if len(values) != 1: raise ValueError(f'Expected one raster for {sample["ID"]} {year} {layer}, got {len(values)}')
            f, (raw, row, col) = values[0]
            expected = float(sample[PREFIX + layer])
            actual = raw * .0001 if layer == 'NDVI' else raw
            if not math.isclose(actual, expected, rel_tol=0, abs_tol=0.0000001):
                raise ValueError(f'{sample["ID"]} {year} {layer}: raster {actual}, point {expected}')
            checked.append({'cell_id':sample['ID'], 'year':year, 'layer':layer, 'tiff':f.name, 'row':row, 'col':col, 'raw':raw, 'value':actual})
    if len(checked) != 27: raise ValueError(f'Expected 27 comparisons, got {len(checked)}')
    with (TIFS / 'comparison.csv').open('w', newline='') as out:
        writer = csv.DictWriter(out, fieldnames=checked[0].keys(), lineterminator='\n'); writer.writeheader(); writer.writerows(checked)
    print('Matched 27 raster values (3 coordinates × 3 years × 3 layers).')

if __name__ == '__main__': main()
