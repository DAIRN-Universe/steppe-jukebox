"""Focused checks of source separation, persistent EIC frames and the shared job."""
import base64
import io
import json
import threading
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from steppe_jukebox.eic import BASE, EicPalette, FrameClient, frame_name
from steppe_jukebox.gibs import PALETTES, Palette, TileCache, TileClient, png_bytes
from steppe_jukebox.live import LiveJob, load_live_regions
from steppe_jukebox.sound import build_track


@pytest.fixture(scope="module")
def native_frames():
    palette = EicPalette()
    result = {}
    for day, fraction in [("2026-04-20", .3), ("2026-06-10", .7)]:
        color = tuple(map(int, palette.ramp[int(len(palette.ramp)*fraction)]))
        stream = io.BytesIO()
        Image.new("RGB", (8640, 4320), color).save(stream, format="PNG")
        result[day] = stream.getvalue()
    return result


def client(tmp_path, frames):
    calls = []
    def fetch(url):
        calls.append(url)
        if url == BASE:
            return "\n".join(frame_name(day) for day in frames).encode()
        return next(raw for day, raw in frames.items() if url == BASE+frame_name(day))
    return FrameClient(tmp_path, fetch), calls


def test_eic_has_own_five_class_scale_and_exact_mask_colors(monkeypatch):
    monkeypatch.setattr(Palette, "ndvi", lambda *args: (_ for _ in ()).throw(AssertionError("GIBS scale used")))
    palette = EicPalette()
    pixels = [(*palette.ramp[int(len(palette.ramp)*fraction)], 255) for fraction in [.1, .3, .5, .7, .9]]
    pixels += [(255,255,255,255), (8,123,176,255), (1,2,3,255), (1,2,240,255), (100,100,100,128)]
    assert palette.classify(np.array(pixels,dtype=np.uint8)).tolist() == [1,2,3,4,5,0,0,-1,-1,-1]


def test_eic_cache_survives_new_client_and_never_substitutes_missing_date(tmp_path,native_frames):
    first,calls=client(tmp_path,native_frames)
    result=first.fetch("2026-04-20")
    assert result.status=="ok" and not result.from_cache and len(calls)==2
    second=FrameClient(tmp_path,lambda url: (_ for _ in ()).throw(AssertionError("Network used")))
    warm=second.fetch("2026-04-20")
    assert warm.from_cache and warm.raw==result.raw and second.network_requests==0
    missing=second.fetch("2026-04-21")
    assert missing.status=="unavailable_date" and missing.raw is None and second.network_requests==0


@pytest.mark.parametrize("corruption",["blob","date","variant","url"])
def test_eic_invalid_cache_record_is_requested_again(tmp_path,native_frames,corruption):
    source,calls=client(tmp_path,native_frames);result=source.fetch("2026-04-20")
    manifest=next(p for p in tmp_path.glob('*.json') if p.name!='catalog.json')
    meta=json.loads(manifest.read_text())
    if corruption=='blob':(tmp_path/(meta['sha256']+'.png')).write_bytes(b'broken')
    else:
        meta['actual_date' if corruption=='date' else 'url' if corruption=='url' else 'identity']='wrong';manifest.write_text(json.dumps(meta))
    restored=source.fetch("2026-04-20")
    assert restored.status=='ok' and not restored.from_cache
    assert calls[-1]==BASE+frame_name("2026-04-20") and len(calls)==3


def test_eic_bad_image_and_network_error_are_not_cached(tmp_path):
    source=FrameClient(tmp_path,lambda url:b'not PNG')
    assert source.fetch('2026-04-20',['2026-04-20']).status=='invalid_image'
    assert not list(tmp_path.glob('*.png'))
    def offline(url):raise OSError('offline')
    assert FrameClient(tmp_path,offline).fetch('2026-04-20',['2026-04-20']).status=='request_error'


def test_eic_clear_and_cancelled_catalog_cannot_repopulate_cache(tmp_path,native_frames):
    source,calls=client(tmp_path,native_frames);source.fetch('2026-04-20')
    keep=tmp_path/'keep.txt';keep.write_text('Unrelated')
    assert source.clear()>=4 and keep.read_text()=='Unrelated'
    assert source.cached('2026-04-20') is None
    cancel=threading.Event()
    def fetch(url):
        cancel.set()
        return frame_name('2026-04-20').encode()
    assert FrameClient(tmp_path,fetch).catalog(cancel=cancel)==['2026-04-20']
    assert not (tmp_path/'catalog.json').exists()


def test_live_eic_journey_uses_each_step_date_without_gibs(tmp_path,native_frames):
    regions=load_live_regions();base=regions['kostanay']
    region=replace(base,dates=tuple('2026-04-20' if i<24 else '2026-06-10' for i in range(48)))
    eic,calls=client(tmp_path,native_frames)
    gibs=TileClient(TileCache(tmp_path/'gibs'),lambda key:(_ for _ in ()).throw(AssertionError('GIBS used for EIC')))
    job=LiveJob('journey',region,'eic','journey','2026-04-20',eic=eic,gibs=gibs).start();job.thread.join(20)
    result=job.payload()
    assert result['state']=='ready',getattr(job,'detail',None)
    assert len(result['maps'])==2 and len(calls)==3 and gibs.network_requests==0
    assert [slot['date'] for slot in result['track']['intervals']]==list(region.dates)
    classes=(2,)*24+(4,)*24
    assert base64.b64decode(result['track']['audio_src'].split(',',1)[1])==build_track(region.route,classes).wav


def test_live_eic_missing_journey_dates_block_without_downloads(tmp_path,native_frames):
    source,calls=client(tmp_path,native_frames)
    job=LiveJob('missing',load_live_regions()['kostanay'],'eic','journey','2026-04-20',eic=source).start();job.thread.join(10)
    result=job.payload()
    assert result['state']=='error' and result['error']=='unavailable_dates'
    assert result['track'] is None and not result['maps'] and result['missing_dates']
    assert calls==[BASE]


def test_live_gibs_uses_loader_classes_instead_of_saved_season(tmp_path):
    palette=Palette(PALETTES/'ndvi.xml')
    rgb=next(rgb for rgb in palette.entries if palette.ndvi((*rgb,255)).get('ndvi_class')==2)
    stream=io.BytesIO();Image.new('RGBA',(512,512),(*rgb,255)).save(stream,format='PNG');raw=stream.getvalue()
    source=TileClient(TileCache(tmp_path),lambda key:(raw,{'actual_date':key.date+'T00:00:00Z'}))
    region=load_live_regions()['kostanay'];job=LiveJob('gibs',region,'gibs','fixed','2026-04-15',gibs=source).start();job.thread.join(15)
    result=job.payload()
    assert result['state']=='ready',getattr(job,'detail',None)
    # The saved KST-006 is missing on this date; the injected source has class 2.
    assert result['track']['intervals'][5]['ndvi_class']==2
    assert source.network_requests==15
    assert base64.b64decode(result['track']['audio_src'].split(',',1)[1])==build_track(region.route,(2,)*48).wav
