from datetime import datetime, timezone
import pytest
from app.analysis import sample_route, align_weather, classify_risk


def weather(**kw):
    data={'temperature_2m':10.0,'precipitation':0.0,'wind_speed_10m':0.0,'visibility':10000,'weather_code':0}
    return data | kw


@pytest.mark.parametrize('rain,expected', [(0.49,0),(0.5,1),(2.5,2),(8,3),(16,3),(16.01,4)])
def test_rain_threshold_boundaries(rain, expected):
    assert classify_risk(weather(precipitation=rain))['level']==expected


@pytest.mark.parametrize('visibility,expected',[(5000,1),(2000,1),(1999,2),(1000,2),(999,3),(500,3),(499,4)])
def test_visibility_boundaries(visibility, expected):
    assert classify_risk(weather(visibility=visibility))['level']==expected


def test_combined_risk_takes_highest_and_visibility_inference_is_marked():
    r=classify_risk(weather(visibility=None,weather_code=45,wind_speed_10m=7))
    assert r['level']==3 and r['visibility_source']=='推断'


def test_sampling_keeps_segment_junction_and_time_uses_each_segment_speed():
    segments=[{'geometry':{'type':'LineString','coordinates':[[114,30],[114,30.18]]},'distance':20000,'duration':3600},
              {'geometry':{'type':'LineString','coordinates':[[114,30.18],[114,30.36]]},'distance':20000,'duration':7200}]
    start=datetime(2025,1,1,tzinfo=timezone.utc)
    result=sample_route(segments,start,spacing_m=20000)
    assert len(result)==3
    assert result[1]['position']==[114,30.18]
    assert result[1]['elapsed_seconds']==pytest.approx(3600)
    assert result[-1]['elapsed_seconds']==pytest.approx(10800)


def test_weather_aligns_to_nearest_utc_hour_and_rejects_outside_range():
    forecasts={'time':['2025-01-01T00:00','2025-01-01T01:00'],'precipitation':[1,2]}
    assert align_weather(datetime(2025,1,1,0,40,tzinfo=timezone.utc),forecasts)['precipitation']==2
    with pytest.raises(ValueError,match='预报范围'):
        align_weather(datetime(2025,1,1,2,0,tzinfo=timezone.utc),forecasts)

@pytest.mark.parametrize('speed,expected',[(5.49,0),(5.5,1),(10.8,2),(13.9,3),(17.2,3),(17.21,4)])
def test_wind_threshold_boundaries(speed, expected):
    assert classify_risk(weather(wind_speed_10m=speed))['level']==expected

@pytest.mark.parametrize('temp,expected',[(-2.1,4),(-2,3),(-0.1,3),(0,2),(2,2),(2.1,0)])
def test_freezing_rain_boundaries(temp, expected):
    assert classify_risk(weather(temperature_2m=temp,precipitation=0.1))['level']==expected


def test_unknown_weather_code_does_not_imply_complete_risk():
    result=classify_risk(weather(weather_code=999))
    assert result['factors']['天气码'] is None and result['incomplete'] is True


def test_nonfinite_weather_is_rejected():
    with pytest.raises(ValueError,match='天气'):
        classify_risk(weather(precipitation=float('nan')))
