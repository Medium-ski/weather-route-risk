"""Open-Meteo 天气及带来源的离线历史预报快照。"""
from datetime import datetime, timezone
from hashlib import sha256
import json
import logging
import os
from pathlib import Path
from time import monotonic, time
import httpx

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT/'fixtures'/'weather'/'historical_forecasts.json'
URL = 'https://api.open-meteo.com/v1/forecast'
VARIABLES = 'temperature_2m,precipitation,precipitation_probability,weather_code,wind_speed_10m,wind_gusts_10m,visibility'
logger = logging.getLogger(__name__)


class WeatherUnavailable(Exception):
    """天气不可用时禁止编造数值。"""


def _key(point):
    return f'{point[0]:.5f},{point[1]:.5f}'


def _offline(points):
    if not FIXTURE.exists(): raise WeatherUnavailable('天气数据不可用：没有离线快照')
    fixture=json.loads(FIXTURE.read_text(encoding='utf-8'))
    try:
        return [{'mode':'fixture','source':fixture['source'],'retrieved_at_utc':fixture['retrieved_at_utc'],
                 'source_url':fixture['source_url'], 'data_kind':fixture['data_kind'],
                 'weather':fixture['records'][_key(point)]} for point in points]
    except KeyError as exc:
        raise WeatherUnavailable('天气数据不可用：离线快照未覆盖该采样点') from exc


def fetch_weather(points, *, offline=False, transport=None, cache_dir=None):
    if not points: return []
    if offline: return _offline(points)
    cache_dir=Path(cache_dir) if cache_dir is not None else ROOT/'cache'
    cache_dir.mkdir(parents=True,exist_ok=True)
    results=[]
    with httpx.Client(timeout=5.0,transport=transport) as client:
        for index in range(0,len(points),50):
            batch=points[index:index+50]
            params={'latitude':','.join(f'{p[0]:.5f}' for p in batch),
                    'longitude':','.join(f'{p[1]:.5f}' for p in batch),
                    'hourly':VARIABLES,'timezone':'UTC','forecast_days':'3','wind_speed_unit':'ms'}
            request=client.build_request('GET',URL,params=params)
            cache_file=cache_dir/(sha256(str(request.url).encode()).hexdigest()+'.json')
            data=None
            if cache_file.exists():
                try:
                    cached=json.loads(cache_file.read_text(encoding='utf-8'))
                    if 0 <= time()-cached['cached_at'] < float(os.getenv('CACHE_TTL_MIN','30'))*60: data=cached['payload']
                except (OSError,ValueError,KeyError): pass
            if data is None:
                for _ in range(2):
                    started=monotonic(); status='连接失败'
                    try:
                        response=client.send(request); status=str(response.status_code); response.raise_for_status()
                        payload=response.json(); data=payload if isinstance(payload,list) else [payload]
                        if len(data)!=len(batch) or any(not isinstance(item.get('hourly'),dict) or not set(['time',*VARIABLES.split(',')]).issubset(item['hourly']) or not item['hourly']['time'] or any(len(v)!=len(item['hourly']['time']) for v in item['hourly'].values()) for item in data):
                            raise ValueError('天气坐标数量或字段不匹配')
                        record={'cached_at':time(),'payload':data}
                        cache_file.write_text(json.dumps(record,ensure_ascii=False),encoding='utf-8')
                        retrieved=datetime.now(timezone.utc).isoformat()
                        break
                    except (httpx.HTTPError,ValueError) as exc:
                        logger.warning('天气请求失败: %s',exc); data=None
                    finally:
                        logger.info('天气请求 URL=%s 耗时=%.3fs 状态=%s',request.url,monotonic()-started,status)
                if data is None:
                    return _offline(points)
            else:
                retrieved=datetime.fromtimestamp(cached['cached_at'],timezone.utc).isoformat()
            results.extend({'mode':'live','source':'Open-Meteo 实时预报','source_url':str(request.url),
                            'retrieved_at_utc':retrieved,'data_kind':'forecast','weather':item} for item in data)
    return results
