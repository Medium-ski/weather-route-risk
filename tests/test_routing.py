import httpx
import pytest

from app.routing import RouteUnavailable, get_route

WUHAN = (30.59, 114.30)
HENGYANG = (26.89, 112.57)


def test_offline_uses_saved_osrm_geometry():
    result = get_route(WUHAN, HENGYANG, offline=True)
    assert result['mode'] == 'fixture'
    assert result['retrieved_at_utc']
    assert len(result['response']['routes']) >= 2
    assert len(result['response']['routes'][0]['geometry']['coordinates']) > 2


def test_offline_uncached_route_is_explicitly_unavailable():
    with pytest.raises(RouteUnavailable, match='未缓存'):
        get_route((10.0, 100.0), (11.0, 101.0), offline=True)


def test_network_failure_retries_once_then_uses_fixture():
    calls = []
    def unavailable(request):
        calls.append(request)
        raise httpx.ConnectError('network unavailable', request=request)
    result = get_route(WUHAN, HENGYANG, transport=httpx.MockTransport(unavailable))
    assert len(calls) == 2
    assert result['mode'] == 'fixture'


def test_live_result_is_returned_with_real_source():
    def respond(request):
        assert request.url.params['alternatives'] == '3'
        return httpx.Response(200, json={'code':'Ok','routes':[{'distance':10,'duration':5,'geometry':{'type':'LineString','coordinates':[[1,2],[2,3],[3,4]]}}]})
    result = get_route(WUHAN, HENGYANG, transport=httpx.MockTransport(respond))
    assert result['mode'] == 'live'
    assert result['source'] == 'OSRM / OpenStreetMap'
    assert result['response']['routes'][0]['distance'] == 10
