"""Preset places are the initial editable points, with one numbered marker per place."""
import pytest
from playwright.sync_api import expect
from test_browser import browser, running_app
from test_live_browser import transport, ui, load
from test_route_browser import remove_all,pick,enable_points

pytestmark=pytest.mark.browser


@pytest.mark.parametrize('region,names,keys,steps,duration',[
    ('kostanay',['Каменное озеро','Наурзум','Аккум'],['261/1066','271/1066','289/1074'],48,24),
    ('north-kazakhstan',['Петропавл','Булаево','Тайынша'],['249/1090','249/1095','257/1093'],14,7),
    ('pavlodar',['Павлодар','Аксу','Баянаул'],['268/1124','269/1124','278/1118'],11,5.5),
    ('west-kazakhstan',['Уральск','Чапаев'],['275/1012','283/1011'],9,4.5),
    ('aktobe',['Актобе','Хромтау'],['282/1037','282/1043'],7,3.5),
    ('karaganda',['Караганда','Каркаралинск'],['285/1107','288/1117'],11,5.5),
    ('abai',['Семей','Кайнар','Аягоз'],['281/1138','292/1134','298/1139'],18,9),
    ('akmola',['Атбасарский заказник','Нацпарк «Кокшетау»','Нацпарк «Бурабай»','Нацпарк «Буйратау»'],['274/1088','265/1090','264/1096','272/1105'],56,28),
])
def test_named_presets_replace_pluses_and_reset_without_changing_track(browser,tmp_path,monkeypatch,region,names,keys,steps,duration):
    transport(tmp_path,monkeypatch)
    with running_app(None,tmp_path/'presets.log',live=True) as url:
        ctx,page,f=ui(browser,url);errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        f.locator('#region').select_option(region)
        expect(f.locator('#route-coordinate-list li')).to_have_count(len(names))
        assert f.locator('.route-point-name').all_text_contents()==names
        assert f.evaluate('steppeLive.draft')==keys
        expect(f.locator('.route-waypoint')).to_have_count(len(names))
        for i,(key,name) in enumerate(zip(keys,names,strict=True)):
            marker=f.locator(f'.route-waypoint[data-waypoint-key="{key}"]')
            expect(marker.locator('text')).to_have_text(str(i+1))
            expect(marker.locator('title')).to_have_text(f'{i+1} · {name}')
        expect(f.locator('.route-landmark')).to_have_count(0)
        expect(f.locator('#toggle')).to_be_disabled()
        load(f)
        assert f.evaluate('steppeLive.request.track.intervals.length')==steps
        assert f.evaluate('steppeLive.request.track.duration_s')==duration
        assert f.evaluate('document.querySelector("audio").paused')
        enable_points(f);remove_all(f);pick(f,keys[0]);load(f)
        assert f.evaluate('steppeLive.request.track.intervals.length')==1
        f.locator('#reset-route').click()
        assert f.evaluate('steppeLive.draft')==keys
        assert f.locator('.route-point-name').all_text_contents()==names
        expect(f.locator('.route-waypoint')).to_have_count(len(names))
        for lang in ['kk','en','ru']:
            f.locator('#language').select_option(lang)
            assert 'undefined' not in f.locator('#route-points').inner_text()
            for width in [1280,390,320]:
                page.set_viewport_size({'width':width,'height':844})
                assert f.evaluate('document.documentElement.scrollWidth<=innerWidth')
        assert not errors,errors
        ctx.close()
