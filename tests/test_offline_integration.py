import json
from datetime import datetime, timezone
from pathlib import Path
import pytest
from app.routing import get_route
from app.route_parser import parse_route, route_segments
from app.analysis import sample_route, align_weather, classify_risk
from app.weather import fetch_weather

ROOT=Path(__file__).resolve().parent.parent

@pytest.mark.parametrize('case_file',sorted((ROOT/'fixtures'/'cases').glob('*.json')))
def test_real_route_and_historical_weather_pipeline(case_file):
    case=json.loads(case_file.read_text(encoding='utf-8'))
    if case['type']=='alternative':
        route=get_route((30.59,114.3),(26.89,112.57),offline=True)['response']['routes'][case['route_index']]
        segments=[route]
    else:
        segments=route_segments(parse_route(case['route_text']),offline=True)
    samples=sample_route(segments,datetime.fromisoformat(case['departure_utc']))
    data=fetch_weather([(p['position'][1],p['position'][0]) for p in samples],offline=True)
    levels=[classify_risk(align_weather(datetime.fromisoformat(s['passage_utc']),w['weather']['hourly']))['level'] for s,w in zip(samples,data)]
    assert len(samples)==case['expected']['samples']
    assert max(levels)==case['expected']['highest_risk']
    assert round(samples[-1]['distance_m'])==case['expected']['distance_m']
    assert all(w['data_kind']=='historical_forecast' for w in data)
    assert '不是当前预报' in data[0]['source']


def test_pipeline_analyzes_real_route_and_historical_forecast():
    from app.analysis import analyze_route
    route=get_route((30.59,114.3),(26.89,112.57),offline=True)['response']['routes'][0]
    result=analyze_route([route],datetime(2025,1,1,tzinfo=timezone.utc),offline=True)
    assert len(result)==26
    assert all(r['weather_source']['mode']=='fixture' for r in result)
    assert all('forecast_time_utc' in r['weather'] and 'level' in r['risk'] for r in result)


def test_entire_offline_pipeline_makes_no_http_client(monkeypatch):
    import httpx
    from app.analysis import analyze_route
    def deny(*args,**kwargs): raise AssertionError('离线流程不应创建网络客户端')
    monkeypatch.setattr(httpx,'Client',deny)
    route=get_route((30.59,114.3),(26.89,112.57),offline=True)['response']['routes'][0]
    result=analyze_route([route],datetime(2025,1,1,tzinfo=timezone.utc),offline=True)
    assert result and all(r['weather_source']['mode']=='fixture' for r in result)
