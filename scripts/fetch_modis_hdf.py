"""Download the pilot's original NASA HDF4 files to a directory outside the repo."""
import os
import concurrent.futures
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def main(destination):
    output = Path(destination).resolve()
    if output == ROOT or ROOT in output.parents:
        raise ValueError('Store the large source files outside the worktree')
    output.mkdir(parents=True, exist_ok=True)
    urls = (ROOT / 'data/modis-pilot/steppe-jukebox-mod13q1-pilot-granule-list.txt').read_text().splitlines()
    with tempfile.TemporaryDirectory(prefix='steppe-edl-') as temp:
        def download(url):
            target = output / url.rsplit('/', 1)[-1]
            temporary = target.with_suffix('.hdf.part')
            if target.exists():
                print('Already present:', target.name, flush=True)
                return
            cookies = Path(temp) / (target.name + '.cookies')
            cookies.touch(mode=0o600)
            print('Downloading:', target.name, flush=True)
            for attempt in range(1, 11):
                result = subprocess.run(['curl', '--fail', '--silent', '--show-error', '--location', '--netrc', '--cookie', str(cookies), '--cookie-jar', str(cookies), '--retry', '3', '--retry-all-errors', '--connect-timeout', '30', '--max-time', '600', '--continue-at', '-', '--output', str(temporary), url])
                if result.returncode == 0: break
                print('Retrying:', target.name, 'attempt:', attempt, flush=True)
            else: raise RuntimeError(f'Download failed after 10 attempts: {target.name}')
            with temporary.open('rb') as source:
                if source.read(4) != bytes.fromhex('0e031301'): raise ValueError(f'Not an HDF4 file: {target.name}')
            os.replace(temporary, target)
            print('Completed:', target.name, target.stat().st_size, flush=True)
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as workers:
            list(workers.map(download, urls))

if __name__ == '__main__': main(sys.argv[1])
