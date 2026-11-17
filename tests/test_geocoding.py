import pytest
from app.geocoding import resolve_place, search_places


def provider(query):
    assert query in ('北京','朝阳','不存在')
    data={
      '北京':[
        {'name':'北京','admin1':'北京市','admin2':'北京市','country':'中国','latitude':39.9075,'longitude':116.39723,'feature_code':'PPLC'},
        {'name':'北京','admin1':'重庆市','admin2':'重庆市','country':'中国','latitude':30.72,'longitude':108.67,'feature_code':'PPL'}],
      '朝阳':[
        {'name':'朝阳','admin1':'辽宁','admin2':'朝阳市','country':'中国','latitude':41.57,'longitude':120.45,'feature_code':'PPLA2'},
        {'name':'朝阳','admin1':'北京市','admin2':'北京市','country':'中国','latitude':39.92,'longitude':116.44,'feature_code':'PPLA2'}],
      '不存在':[]}
    return {'results':data[query],'source':'Open-Meteo Geocoding / GeoNames','source_url':'https://geocoding-api.open-meteo.com/v1/search','retrieved_at_utc':'2026-11-17T00:00:00+00:00'}


def test_live_resolves_beijing_with_real_source():
    result=resolve_place('北京',search=provider)
    assert result['position']==(39.9075,116.39723)
    assert result['source']=='Open-Meteo Geocoding / GeoNames'
    assert result['retrieved_at_utc']


def test_same_name_requires_qualifier_and_qualified_selection_is_exact():
    with pytest.raises(ValueError,match='同名'):
        resolve_place('朝阳',search=provider)
    choices=search_places('朝阳',search=provider)
    assert len(choices)==2
    chosen=resolve_place(choices[0]['label'],search=provider)
    assert chosen['position']==(41.57,120.45)


def test_offline_unknown_place_fails_without_internet():
    def fail(_): raise AssertionError('离线模式不应请求网络')
    with pytest.raises(ValueError,match='离线'):
        resolve_place('北京',offline=True,search=fail)


def test_builtin_and_coordinates_need_no_external_geocoder():
    def fail(_): raise AssertionError('不应调用网络')
    assert resolve_place('广州',offline=True,search=fail)['position']==(23.13,113.26)
    assert resolve_place('39.9,116.4',offline=True,search=fail)['position']==(39.9,116.4)


def test_missing_place_explains_input_options():
    with pytest.raises(ValueError,match='未找到'):
        resolve_place('不存在',search=provider)
