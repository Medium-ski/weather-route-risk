import pytest
from app.route_parser import parse_route, route_segments
from app.routing import RouteUnavailable


def test_parse_city_names_and_latlon():
    assert parse_route('武汉 → 咸宁 → 长沙 → 衡阳')==[(30.59,114.3),(29.84,114.32),(28.23,112.94),(26.89,112.57)]
    assert parse_route('30.59,114.30; 29.84,114.32')==[(30.59,114.30),(29.84,114.32)]


def test_parse_geojson_lonlat():
    assert parse_route('{"type":"LineString","coordinates":[[114.3,30.59],[114.32,29.84]]}')==[(30.59,114.3),(29.84,114.32)]


def test_unreachable_segment_does_not_make_up_line():
    def fail(*args,**kwargs): raise RouteUnavailable('不可达')
    with pytest.raises(RouteUnavailable,match='第 1 段不可达'):
        route_segments([(30.59,114.30),(29.84,114.32)],router=fail)


def test_city_route_can_resolve_non_builtin_places_without_straight_lines():
    positions={'北京':(39.9,116.4),'广州':(23.13,113.26)}
    assert parse_route('北京 → 广州',resolver=lambda name: positions[name])==[(39.9,116.4),(23.13,113.26)]
