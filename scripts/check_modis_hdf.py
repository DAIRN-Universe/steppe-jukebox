"""Verify AppEEARS point samples directly against NASA MOD13Q1 HDF4 files.

Usage: python scripts/check_modis_hdf.py /path/to/hdf-directory
Requires the HDF4 mfhdf shared library. A missing or unreadable granule fails.
"""
import csv
import argparse
import ctypes
import ctypes.util
import hashlib
import math
from pathlib import Path

libname = ctypes.util.find_library('mfhdfalt') or ctypes.util.find_library('mfhdf')
if not libname: raise RuntimeError('HDF4 mfhdf shared library is required')
hdf = ctypes.CDLL(libname)
for name, args in {
    'SDstart': [ctypes.c_char_p, ctypes.c_int32],
    'SDnametoindex': [ctypes.c_int32, ctypes.c_char_p],
    'SDselect': [ctypes.c_int32, ctypes.c_int32],
    'SDreaddata': [ctypes.c_int32, ctypes.POINTER(ctypes.c_int32), ctypes.POINTER(ctypes.c_int32), ctypes.POINTER(ctypes.c_int32), ctypes.c_void_p],
    'SDendaccess': [ctypes.c_int32], 'SDend': [ctypes.c_int32],
}.items():
    fn = getattr(hdf, name); fn.argtypes = args; fn.restype = ctypes.c_int32

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data/modis-pilot'
PREFIX = 'MOD13Q1_061__250m_16_days_'
LAYERS = {'NDVI': '250m 16 days NDVI', 'VI_Quality': '250m 16 days VI Quality', 'pixel_reliability': '250m 16 days pixel reliability'}

def main(directory, available_only=False):
    directory = Path(directory)
    with (DATA / 'steppe-jukebox-mod13q1-pilot-MOD13Q1-061-results.csv').open() as f:
        rows = list(csv.DictReader(f))
    urls = (DATA / 'steppe-jukebox-mod13q1-pilot-granule-list.txt').read_text().splitlines()
    granules = {Path(url).name for url in urls}
    if len(granules) != 9: raise ValueError('Expected nine original granules')
    available = {name for name in granules if (directory / name).is_file()}
    if not available_only and available != granules:
        raise FileNotFoundError('Missing original granules: ' + ', '.join(sorted(granules - available)))
    if not available: raise FileNotFoundError(f'No source granules in {directory}')
    checks, manifest = [], []
    for filename in sorted(available):
        path = directory / filename
        if not path.is_file(): raise FileNotFoundError(path)
        with path.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        year, tile = filename[9:13], filename.split('.')[2]
        selected = [row for row in rows if row['Date'].startswith(year) and row['MODIS_Tile'] == tile]
        if not selected: raise ValueError(f'No route samples in {filename}')
        dataset = hdf.SDstart(str(path).encode(), 1)  # DFACC_READ
        if dataset < 0: raise ValueError(f'Cannot open HDF4 {path}')
        try:
            for sample in selected:
                y = int(float(sample['MOD13Q1_061_Line_Y_250m']))
                x = int(float(sample['MOD13Q1_061_Sample_X_250m']))
                for layer, name in LAYERS.items():
                    index = hdf.SDnametoindex(dataset, name.encode())
                    if index < 0: raise ValueError(f'No HDF layer {name} in {filename}')
                    sds = hdf.SDselect(dataset, index)
                    if sds < 0: raise ValueError(f'Cannot select {name} in {filename}')
                    value_type = {'NDVI': ctypes.c_int16, 'VI_Quality': ctypes.c_uint16, 'pixel_reliability': ctypes.c_int8}[layer]
                    result = value_type()
                    start = (ctypes.c_int32 * 2)(y, x)
                    edge = (ctypes.c_int32 * 2)(1, 1)
                    try:
                        if hdf.SDreaddata(sds, start, None, edge, ctypes.byref(result)) < 0: raise ValueError(f'Cannot read {name} at {y},{x}')
                        raw = result.value
                    finally: hdf.SDendaccess(sds)
                    value = raw * .0001 if layer == 'NDVI' and raw != -3000 else raw
                    expected = float(sample[PREFIX + layer])
                    if not math.isclose(value, expected, rel_tol=0, abs_tol=1e-7):
                        raise ValueError(f'{sample["ID"]} {year} {layer}: HDF={value}, AppEEARS={expected}')
                    checks.append({'cell_id':sample['ID'], 'year':year, 'layer':layer, 'granule':filename, 'line':y, 'sample':x, 'raw':raw, 'value':value})
        finally: hdf.SDend(dataset)
        manifest.append({'file':filename,'size_bytes':path.stat().st_size,'sha256':digest})
    expected_count = 3 * sum(1 for row in rows if any(row['Date'][:4] == name[9:13] and row['MODIS_Tile'] == name.split('.')[2] for name in available))
    if len(checks) != expected_count: raise ValueError(f'Expected {expected_count} comparisons, got {len(checks)}')
    suffix = '-partial' if available != granules else ''
    for name, data in [(f'hdf-comparison{suffix}.csv', checks), (f'hdf-manifest{suffix}.csv', manifest)]:
        with (DATA / name).open('w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=data[0].keys(), lineterminator='\n'); writer.writeheader(); writer.writerows(data)
    print(f'Matched {len(checks)} HDF values across {len(available)} of {len(granules)} granules.')

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--available-only', action='store_true', help='Check only completed HDF files; label output as partial')
    args = parser.parse_args()
    main(args.directory, args.available_only)
