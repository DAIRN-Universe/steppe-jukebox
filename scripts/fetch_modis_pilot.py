"""Submit and download the pilot's NASA AppEEARS point extraction."""
import base64
import csv
import json
import netrc
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API = 'https://appeears.earthdatacloud.nasa.gov/api/'
OUTPUT = ROOT / 'data/modis-pilot'

def request(path, token=None, data=None, basic=None):
    headers = {}
    if token: headers['Authorization'] = 'Bearer ' + token
    if basic: headers['Authorization'] = 'Basic ' + basic
    if data is not None: headers['Content-Type'] = 'application/json'
    req = urllib.request.Request(API + path, data=json.dumps(data).encode() if data is not None else None, headers=headers, method='POST' if data is not None or basic else 'GET')
    with urllib.request.urlopen(req, timeout=120) as response: return response.read()

def main():
    credentials = netrc.netrc().authenticators('urs.earthdata.nasa.gov')
    if not credentials: raise RuntimeError('Earthdata Login is not configured in ~/.netrc')
    basic = base64.b64encode((credentials[0] + ':' + credentials[2]).encode()).decode()
    token = json.loads(request('login', basic=basic))['token']
    with (ROOT / 'data/real-test/noaa20-kostanay/route.csv').open() as f:
        points = [{'id': row['cell_id'], 'latitude': float(row['lat']), 'longitude': float(row['lon'])} for row in csv.DictReader(f)]
    layers = ['_250m_16_days_NDVI', '_250m_16_days_VI_Quality', '_250m_16_days_pixel_reliability']
    task = {'task_type': 'point', 'task_name': 'steppe-jukebox-mod13q1-pilot', 'params': {'dates': [{'startDate': f'07-12-{y}', 'endDate': f'07-12-{y}'} for y in (2001, 2013, 2025)], 'layers': [{'product': 'MOD13Q1.061', 'layer': layer} for layer in layers], 'coordinates': points}}
    task_id = json.loads(request('task', token, task))['task_id']
    print('AppEEARS task:', task_id, flush=True)
    while True:
        status = json.loads(request('task/' + task_id, token))
        if status['status'] == 'done': break
        if status['status'] in ('error', 'failed'): raise RuntimeError(f'AppEEARS task failed: {status.get("error")}')
        time.sleep(15)
    bundle = json.loads(request('bundle/' + task_id, token))
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for f in bundle['files']:
        name = Path(f['file_name']).name
        if name == 'README.md': continue
        payload = request('bundle/' + task_id + '/' + f['file_id'], token)
        if name.endswith('-request.json'):
            metadata = json.loads(payload)
            metadata.pop('user_id', None)
            payload = json.dumps(metadata, indent=2).encode() + b'\n'
        (OUTPUT / name).write_bytes(payload)
        print('Downloaded', name, flush=True)

if __name__ == '__main__': main()
