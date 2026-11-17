"""OSRM 路由与有限范围的离线真实路线快照。"""
from datetime import datetime, timezone
import json
import logging
import math
from pathlib import Path
from time import monotonic
from urllib.parse import urlsplit

import httpx

logger = logging.getLogger(__name__)
FIXTURES = Path(__file__).resolve().parent.parent / 'fixtures' / 'routes'
OSRM = 'https://router.project-osrm.org/route/v1/driving'


class RouteUnavailable(Exception):
    """线路不可达或离线数据没有覆盖该路段。"""


def _fixture(start, end):
    for path in FIXTURES.glob('*.json'):
        data = json.loads(path.read_text(encoding='utf-8'))
        coordinates = urlsplit(data['source_url']).path.rsplit('/', 1)[-1].split(';')
        points = [tuple(reversed(tuple(map(float, part.split(','))))) for part in coordinates]
        if all(abs(a-b) < 1e-7 for x, y in zip((start, end), points) for a, b in zip(x, y)):
            return {'mode': 'fixture', **data}
    raise RouteUnavailable('该路段未缓存，离线时不可用')


def get_route(start, end, *, offline=False, transport=None):
    """输入 (纬度, 经度)；离线仅返回坐标完全匹配的真实路由快照。"""
    for point in (start, end):
        if len(point) != 2 or not all(isinstance(v, (int, float)) and math.isfinite(v) for v in point) or not (-90 <= point[0] <= 90 and -180 <= point[1] <= 180):
            raise ValueError('无效坐标')
    if offline:
        return _fixture(start, end)
    url = f'{OSRM}/{start[1]},{start[0]};{end[1]},{end[0]}'
    params = {'alternatives': '3', 'overview': 'full', 'geometries': 'geojson'}
    with httpx.Client(timeout=5.0, transport=transport) as client:
        for _ in range(2):
            started = monotonic()
            status = '连接失败'
            try:
                response = client.get(url, params=params)
                status = str(response.status_code)
                response.raise_for_status()
                payload = response.json()
                if payload.get('code') == 'NoRoute':
                    raise RouteUnavailable('该段不可达')
                if payload.get('code') != 'Ok' or not payload.get('routes'):
                    raise ValueError('OSRM 响应缺少路线')
                return {'mode': 'live', 'source': 'OSRM / OpenStreetMap',
                        'source_url': str(response.request.url),
                        'retrieved_at_utc': datetime.now(timezone.utc).isoformat(),
                        'response': payload}
            except (httpx.HTTPError, ValueError) as exc:
                logger.warning('路由请求失败: %s', exc)
            finally:
                logger.info('路由请求 URL=%s 耗时=%.3fs 状态=%s', url, monotonic()-started, status)
    return _fixture(start, end)
