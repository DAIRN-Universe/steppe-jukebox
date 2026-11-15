"""Linked hackathon logo and a compact three-language selector."""
import pytest
from playwright.sync_api import expect
from test_browser import browser,app_url,localized_ui,media,resize_viewport

pytestmark=pytest.mark.browser


@pytest.mark.parametrize('locale,language',[('kk-KZ','kk'),('ru-RU','ru'),('fr-FR','en')])
def test_compact_header_controls_and_logo_link_keep_playback(browser,app_url,locale,language):
    with localized_ui(browser,app_url,locale) as (page,f):
        expect(f.locator('#language')).to_have_value(language)
        assert f.locator('#language option').evaluate_all('nodes=>nodes.map(n=>n.value)')==['kk','en','ru']
        assert f.locator('#system-language').count()==0
        assert f.locator('label[for="language"]').evaluate('e=>e.classList.contains("sr-only")')
        logo=f.get_by_role('link',name='NASA International Space Apps Challenge',exact=True)
        expect(logo).to_have_attribute('href','https://www.spaceappschallenge.org/')
        expect(logo).to_have_attribute('target','_blank')
        expect(logo).to_have_attribute('rel','noopener noreferrer')
        for width in [1280,1024,853,768,390,320]:
            resize_viewport(page,f,width,1000)
            assert f.evaluate('document.documentElement.scrollWidth<=innerWidth')
            positions=f.evaluate('''()=>Object.fromEntries(['.site-header','.brand','.hackathon-logo','.language-field'].map(s=>[s,document.querySelector(s).getBoundingClientRect().toJSON()]))''')
            header,brand,image,select=(positions[x] for x in ['.site-header','.brand','.hackathon-logo','.language-field'])
            assert abs((image['left']+image['right'])/2-(header['left']+header['right'])/2)<1
            assert brand['right']<=image['left']+1 and image['right']<=select['left']+1
            assert select['width']<=110
        resize_viewport(page,f,1280,1000)
        f.locator('#toggle').click();f.wait_for_function('document.querySelector("audio").currentTime>.1')
        context=page.context
        context.route('https://www.spaceappschallenge.org/**',lambda route:route.fulfill(status=200,content_type='text/html',body='<title>Space Apps</title>'))
        f.locator('.brand').focus()
        f.locator('.brand').press('Tab')
        expect(logo).to_be_focused()
        assert logo.evaluate('e=>getComputedStyle(e).outlineStyle')!='none'
        with context.expect_page() as popup:
            logo.press('Enter')
        popup.value.wait_for_url('https://www.spaceappschallenge.org/')
        assert not media(f)['paused']
        popup.value.close()
        f.locator('#toggle').click();paused=media(f)['time']
        for value in ['kk','en','ru']:
            f.locator('#language').select_option(value)
            expect(f.locator('html')).to_have_attribute('lang',value)
            assert media(f)['paused'] and abs(media(f)['time']-paused)<.01
