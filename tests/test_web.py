from fastapi.testclient import TestClient
from app.main import app

client=TestClient(app)
BASE={'mode':'offline','business_mode':'plan','origin':'武汉','destination':'衡阳',
      'departure_utc':'2025-01-01T08:00:00Z','cargo':'普货','promised_hours':12,
      'time_preference':0.5,'money_preference':0.5}


def test_configuration_lists_source_and_assumptions():
    r=client.get('/api/config')
    assert r.status_code==200
    assert '武汉' in r.json()['cities']
    assert 'reason' in r.json()['assumptions']['freight_yuan_per_km']


def test_offline_plan_contains_real_geometry_and_historical_source():
    r=client.post('/api/analyze',json=BASE)
    assert r.status_code==200, r.text
    d=r.json()
    assert len(d['routes'])==2 and d['result']['decision'] is not None
    assert len(d['routes'][0]['segments'][0]['geometry']['coordinates'])>2
    assert d['result']['decision']['samples'][0]['weather_source']['data_kind']=='historical_forecast'
    assert d['reference_kind']=='模拟参考时刻'


def test_offline_inspection_routes_each_segment():
    r=client.post('/api/analyze',json=BASE|{'business_mode':'inspect','route_text':'武汉 → 咸宁 → 长沙 → 衡阳'})
    assert r.status_code==200, r.text
    assert len(r.json()['routes'][0]['segments'])==3
    assert r.json()['result']['decision']


def test_offline_missing_route_does_not_draw_straight_lines():
    r=client.post('/api/analyze',json=BASE|{'origin':'广州','destination':'武汉'})
    assert r.status_code==400 and '未缓存' in r.json()['detail']


def test_report_has_assumptions_and_historical_label():
    r=client.post('/api/report',json=BASE)
    assert r.status_code==200 and 'text/html' in r.headers['content-type']
    assert '数据与假设' in r.text and '历史预报' in r.text and '运价' in r.text
    assert '模拟参考时刻' in r.text


def test_invalid_mode_rejected():
    assert client.post('/api/analyze',json=BASE|{'mode':'invented'}).status_code==422


def test_report_save_stays_in_project_reports_folder(tmp_path,monkeypatch):
    import app.main
    monkeypatch.setattr(app.main,'REPORTS_DIR',tmp_path)
    r=client.post('/api/report/save',json=BASE)
    assert r.status_code==200, r.text
    result=r.json()
    path=tmp_path/result['filename']
    assert path.is_file() and '数据与假设' in path.read_text(encoding='utf-8')
    assert result['relative_path'].startswith('reports/')
    assert client.get(result['url']).status_code==200


def test_live_beijing_name_is_resolved_and_passed_to_real_router(monkeypatch):
    import app.main as main
    import app.geocoding as geocoding
    seen=[]
    provider={'results':[{'name':'北京','admin1':'北京市','admin2':'北京市','country':'中国','latitude':39.9075,'longitude':116.39723,'feature_code':'PPLC'}], 'source':'Open-Meteo Geocoding / GeoNames','source_url':'https://geocoding-api.open-meteo.com/v1/search?name=Beijing','retrieved_at_utc':'2026-11-17T00:00:00+00:00'}
    monkeypatch.setattr(geocoding,'_fetch',lambda query:provider)
    def routing(start,end,*,offline):
        seen.append((start,end,offline))
        return {'mode':'live','source':'测试路由','source_url':'https://example.test/route','retrieved_at_utc':'2026-11-17T00:00:00+00:00','response':{'routes':[{'distance':1000,'duration':600,'geometry':{'type':'LineString','coordinates':[[116.39723,39.9075],[113.26,23.13]]}}]}}
    monkeypatch.setattr(main,'_cached_route',routing)
    monkeypatch.setattr(main,'evaluate_routes',lambda *args,**kw:{'candidates':[],'ranked_routes':[],'decision':None})
    result=client.post('/api/analyze',json=BASE|{'mode':'live','origin':'北京','destination':'广州'})
    assert result.status_code==200, result.text
    assert seen==[((39.9075,116.39723),(23.13,113.26),False)]
    assert result.json()['resolved_places'][0]['source']=='Open-Meteo Geocoding / GeoNames'


def test_place_search_shows_qualified_names(monkeypatch):
    import app.geocoding as geocoding
    monkeypatch.setattr(geocoding,'_fetch',lambda query:{'results':[{'name':'北京','admin1':'北京市','country':'中国','latitude':39.9075,'longitude':116.39723}], 'source':'test','source_url':'https://example.test','retrieved_at_utc':'2026-11-17T00:00:00Z'})
    r=client.get('/api/places',params={'query':'北京'})
    assert r.status_code==200 and r.json()['places'][0]['label']=='北京（北京市 · 中国）'


def test_export_warns_when_route_misses_promised_deadline():
    r=client.post('/api/report',json=BASE|{'promised_hours':1})
    assert r.status_code==200
    assert '预计超过承诺时效' in r.text


def test_report_includes_public_data_attribution_and_license_links():
    r=client.post('/api/report',json=BASE)
    assert r.status_code==200
    assert 'OpenStreetMap contributors' in r.text
    assert 'https://www.openstreetmap.org/copyright' in r.text
    assert 'https://creativecommons.org/licenses/by/4.0/' in r.text
    assert 'GeoNames' in r.text and 'Open-Meteo' in r.text
