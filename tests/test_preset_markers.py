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


def test_abai_diagonal_reveals_only_one_new_route_cell_per_step(browser, tmp_path, monkeypatch):
    transport(tmp_path, monkeypatch)
    with running_app(None, tmp_path/'abai-trail.log', live=True) as url:
        ctx, page, f = ui(browser, url)
        f.locator('#region').select_option('abai')
        load(f)
        f.locator('#step-forward').click()
        for index in range(2, 14):
            expect(f.locator('.route-tile:not([hidden])')).to_have_count(index)
            expect(f.locator('.route-tile.active')).to_have_count(1)
            f.locator('#step-forward').click()
        ctx.close()


@pytest.mark.parametrize('region', ['kostanay', 'akmola', 'north-kazakhstan', 'pavlodar',
                                    'west-kazakhstan', 'aktobe', 'karaganda', 'abai'])
def test_every_route_step_reveals_only_its_sampled_cell(browser, tmp_path, monkeypatch, region):
    transport(tmp_path, monkeypatch)
    with running_app(None, tmp_path/'all-route-trails.log', live=True) as url:
        ctx, page, f = ui(browser, url)
        f.locator('#region').select_option(region)
        load(f)

        def check_trail():
            result = f.evaluate('''() => {
                const map = steppeLive.map, keys = map.config.point_keys;
                const first = new Set(), errors = [];
                for (let i = 0; i < keys.length; i++) {
                    if (keys[i] != null) first.add(keys[i]);
                    map.highlight(i, false);
                    const visible = [...map.nodes].filter(([key, node]) => !node.hasAttribute('hidden')).map(([key]) => key);
                    const active = [...map.nodes].filter(([key, node]) => node.classList.contains('active')).map(([key]) => key);
                    if (visible.length !== first.size || visible.some(key => !first.has(key)) ||
                        (keys[i] != null && (active.length !== 1 || active[0] !== keys[i]))) errors.push(i);
                }
                return errors;
            }''')
            assert not result, (region, result)

        check_trail()
        keys = f.evaluate('Array.from(new Set(steppeLive.map.config.point_keys.filter(Boolean)))')
        selected = [keys[round(i * (len(keys) - 1) / 4)] for i in range(5)]
        enable_points(f); remove_all(f)
        for key in selected: pick(f, key)
        load(f)
        assert f.evaluate('steppeLive.request.state') == 'ready'
        assert f.evaluate('document.querySelector("audio").paused')
        check_trail()
        remove_all(f); pick(f, selected[0]); load(f)
        assert f.evaluate('steppeLive.request.track.intervals.length') == 1
        check_trail()
        ctx.close()
