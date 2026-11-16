"""Fetch native-projection NASA raster subsets for three control points."""
import base64
import csv
import json
import netrc
import time
from pathlib import Path
from fetch_modis_pilot import ROOT, request

def main():
    a = netrc.netrc().authenticators('urs.earthdata.nasa.gov')
    if not a: raise RuntimeError('Earthdata Login is not configured in ~/.netrc')
    basic = base64.b64encode((a[0] + ':' + a[2]).encode()).decode()
    token = json.loads(request('login', basic=basic))['token']
    with (ROOT / 'data/real-test/noaa20-kostanay/route.csv').open() as f:
        points = list(csv.DictReader(f))
    features = []
    for p in (points[0], points[23], points[47]):
        x, y, d = float(p['lon']), float(p['lat']), .012
        features.append({'type':'Feature', 'properties':{'id':p['cell_id']}, 'geometry':{'type':'Polygon', 'coordinates':[[[x-d,y-d],[x+d,y-d],[x+d,y+d],[x-d,y+d],[x-d,y-d]]]}})
    layers = ['_250m_16_days_NDVI', '_250m_16_days_VI_Quality', '_250m_16_days_pixel_reliability']
    task = {'task_type':'area', 'task_name':'steppe-modis-raster-check', 'params':{'dates':[{'startDate':f'07-12-{y}', 'endDate':f'07-12-{y}'} for y in (2001,2013,2025)], 'layers':[{'product':'MOD13Q1.061','layer':layer} for layer in layers], 'geo':{'type':'FeatureCollection','features':features}, 'output':{'format':{'type':'geotiff'},'projection':'native'}}}
    task_id = json.loads(request('task', token, task))['task_id']
    print('AppEEARS raster task:', task_id, flush=True)
    while True:
        status = json.loads(request('task/' + task_id, token))
        if status['status'] == 'done': break
        if status['status'] in ('error', 'failed'): raise RuntimeError(f'AppEEARS task failed: {status.get("error")}')
        time.sleep(15)
    bundle = json.loads(request('bundle/' + task_id, token))
    output = ROOT / 'data/modis-pilot/raster-check'
    output.mkdir(parents=True, exist_ok=True)
    for f in bundle['files']:
        name = Path(f['file_name']).name
        if name == 'README.md': continue
        payload = request('bundle/' + task_id + '/' + f['file_id'], token)
        if name.endswith('-request.json'):
            metadata = json.loads(payload)
            metadata.pop('user_id', None)
            payload = json.dumps(metadata, indent=2).encode() + b'\n'
        (output / name).write_bytes(payload)
        print('Downloaded', name, flush=True)

if __name__ == '__main__': main()
