"""解析输入，并逐段调用真实路由引擎。"""
import json
from pathlib import Path
import re
import math
import yaml
from .routing import get_route, RouteUnavailable

CITIES_PATH = Path(__file__).resolve().parent.parent / 'config' / 'cities.yaml'


def parse_route(text, *, resolver=None):
    cities = yaml.safe_load(CITIES_PATH.read_text(encoding='utf-8'))
    try:
        if text.lstrip().startswith('{'):
            obj = json.loads(text)
            if obj.get('type') != 'LineString':
                raise ValueError('只支持 GeoJSON LineString')
            points = [(float(c[1]), float(c[0])) for c in obj['coordinates'] if len(c) >= 2]
            if len(points) != len(obj['coordinates']):
                raise ValueError('GeoJSON 坐标不完整')
        elif ';' in text or re.match(r'^\s*[+-]?\d', text):
            points = [tuple(map(float, s.strip().split(','))) for s in text.split(';')]
        else:
            points = [tuple(resolver(name.strip()) if resolver is not None else cities[name.strip()]) for name in re.split(r'\s*(?:→|->)\s*', text)]
    except (KeyError, TypeError, IndexError, json.JSONDecodeError) as exc:
        raise ValueError('路线格式或城市名称无效') from exc
    if len(points) < 2 or any(len(p) != 2 or not all(math.isfinite(v) for v in p) or not (-90 <= p[0] <= 90 and -180 <= p[1] <= 180) for p in points):
        raise ValueError('路线需要至少两个有效坐标')
    return points


def route_segments(points, *, offline=False, router=get_route):
    result = []
    for index, (start, end) in enumerate(zip(points, points[1:]), 1):
        try:
            route = router(start, end, offline=offline)
            result.append({'route': route['response']['routes'][0], 'source': route['source'],
                           'source_url': route['source_url'], 'retrieved_at_utc': route['retrieved_at_utc'],
                           'mode': route['mode'], 'start': start, 'end': end})
        except RouteUnavailable as exc:
            raise RouteUnavailable(f'第 {index} 段不可达：{exc}') from exc
    return result
