import httpx
import pytest
from app.weather import fetch_weather, WeatherUnavailable


def test_weather_batches_at_most_50_and_requests_ms(tmp_path):
    calls=[]
    def respond(req):
        calls.append(req)
        count=len(req.url.params['latitude'].split(','))
        result=[{'latitude':1,'longitude':2,'hourly':{'time':['2025-01-01T00:00'], **{name:[2] for name in ('temperature_2m','precipitation','precipitation_probability','weather_code','wind_speed_10m','wind_gusts_10m','visibility')}}} for _ in range(count)]
        return httpx.Response(200,json=result if count>1 else result[0])
    result=fetch_weather([(30.0,114.0)]*51,transport=httpx.MockTransport(respond),cache_dir=tmp_path)
    assert len(result)==51 and len(calls)==2
    assert calls[0].url.params['wind_speed_unit']=='ms'


def test_unavailable_weather_does_not_invent_values(tmp_path):
    def fail(req): raise httpx.ConnectError('offline',request=req)
    with pytest.raises(WeatherUnavailable,match='天气数据不可用'):
        fetch_weather([(0,0)],transport=httpx.MockTransport(fail),cache_dir=tmp_path)


def test_malformed_live_response_is_not_used(tmp_path):
    def malformed(req):
        return httpx.Response(200,json={'hourly': {'time': ['2025-01-01T00:00']}})
    with pytest.raises(WeatherUnavailable,match='天气数据不可用'):
        fetch_weather([(0,0)],transport=httpx.MockTransport(malformed),cache_dir=tmp_path)
