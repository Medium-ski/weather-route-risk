"""沿真实路线采样、UTC 时间对齐与风险分级。"""
from bisect import bisect_left
from datetime import datetime, timedelta, timezone
from math import asin, cos, isfinite, radians, sin, sqrt
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parent.parent


def _distance(a, b):
    lon1, lat1, lon2, lat2 = map(radians, (*a[:2], *b[:2]))
    x = sin((lat2-lat1)/2)**2 + cos(lat1)*cos(lat2)*sin((lon2-lon1)/2)**2
    return 12742000 * asin(min(1, sqrt(x)))


def sample_route(segments, departure, *, spacing_m=None):
    if spacing_m is None:
        spacing_m = yaml.safe_load((ROOT/'config'/'assumptions.yaml').read_text(encoding='utf-8'))['sampling_interval_km']['value'] * 1000
    if departure.tzinfo is None or departure.utcoffset() is None:
        raise ValueError('发车时间必须带时区')
    if spacing_m <= 0 or not segments:
        raise ValueError('采样间距及路线必须有效')
    departure = departure.astimezone(timezone.utc)
    samples = []
    cumulative_m = cumulative_s = 0.0
    next_mark = spacing_m
    for seg_index, segment in enumerate(segments):
        route = segment.get('route', segment)
        coords = route['geometry']['coordinates']
        if route['geometry']['type'] != 'LineString' or len(coords) < 2 or route['distance'] <= 0 or route['duration'] <= 0:
            raise ValueError('路由几何或时长无效')
        lengths = [0.0]
        for a, b in zip(coords, coords[1:]): lengths.append(lengths[-1] + _distance(a, b))
        if not lengths[-1]: raise ValueError('路由几何长度为零')
        end_m = cumulative_m + route['distance']
        marks = [cumulative_m]
        while next_mark < end_m - 1e-7:
            if next_mark > cumulative_m + 1e-7: marks.append(next_mark)
            next_mark += spacing_m
        marks.append(end_m)
        if abs(next_mark-end_m) < 1e-7: next_mark += spacing_m
        for mark in marks:
            fraction = (mark-cumulative_m)/route['distance']
            geometry_mark = fraction * lengths[-1]
            i = min(max(bisect_left(lengths, geometry_mark), 1), len(coords)-1)
            width = lengths[i] - lengths[i-1]
            local = (geometry_mark - lengths[i-1])/width if width else 0
            pos = [coords[i-1][j] + local*(coords[i][j]-coords[i-1][j]) for j in (0,1)]
            seconds = cumulative_s + fraction*route['duration']
            sample = {'position':pos, 'distance_m':mark, 'elapsed_seconds':seconds,
                      'passage_utc':(departure + timedelta(seconds=seconds)).isoformat(),
                      'segment_index':seg_index}
            # Preserve both sides if individually snapped routes do not share an endpoint.
            if samples and abs(samples[-1]['distance_m']-mark) < 1e-7 and _distance(samples[-1]['position'], pos) < 0.01:
                continue
            samples.append(sample)
        cumulative_m, cumulative_s = end_m, cumulative_s + route['duration']
    return samples


def align_weather(passage, hourly):
    if passage.tzinfo is None or passage.utcoffset() is None: raise ValueError('时间必须带时区')
    target = (passage.astimezone(timezone.utc) + timedelta(minutes=30)).replace(minute=0, second=0, microsecond=0)
    times = [datetime.fromisoformat(t.replace('Z','+00:00')).replace(tzinfo=timezone.utc) for t in hourly['time']]
    if target not in times: raise ValueError('预计经过时间超出天气预报范围')
    index = times.index(target)
    if any(len(v) != len(times) for v in hourly.values()): raise ValueError('天气数据长度不一致')
    return {key:value[index] for key,value in hourly.items()} | {'forecast_time_utc':target.isoformat()}


def classify_risk(weather):
    cfg = yaml.safe_load((ROOT/'config'/'thresholds.yaml').read_text(encoding='utf-8'))
    code = weather.get('weather_code')
    rain = weather.get('precipitation'); wind = weather.get('wind_speed_10m'); temp = weather.get('temperature_2m')
    if any(not isinstance(x,(int,float)) or not isfinite(x) for x in (code,rain,wind,temp)) or rain < 0 or wind < 0:
        raise ValueError('风险分级缺少有效天气数据')
    levels = {}
    def upper(v, limits):
        return 4 if v > limits[3] else 3 if v >= limits[2] else 2 if v >= limits[1] else 1 if v >= limits[0] else 0
    levels['降水'] = upper(rain, cfg['precipitation_mm_h'])
    levels['风速'] = upper(wind, cfg['wind_m_s'])
    visibility=weather.get('visibility'); vis_source='真实'
    if visibility is not None and (not isinstance(visibility,(int,float)) or not isfinite(visibility) or visibility < 0):
        raise ValueError('无效能见度天气数据')
    if visibility is None:
        visibility=cfg['inferred_visibility_m'].get(code); vis_source='推断'
    if visibility is None:
        levels['能见度'] = None
    else:
        a,b,c,d=cfg['visibility_m']
        levels['能见度'] = 4 if visibility < d else 3 if visibility < c else 2 if visibility < b else 1 if visibility <= a else 0
    levels['天气码'] = 0 if code == 0 else next((level for level,name in ((4,'red'),(3,'orange'),(2,'yellow'),(1,'blue')) if code in cfg['weather_code'][name]),None)
    a,b,c=cfg['temperature_precip_c']
    levels['低温降水'] = (4 if temp < c else 3 if temp < b else 2 if temp <= a else 0) if rain > 0 else 0
    level=max(x for x in levels.values() if x is not None)
    return {'level':level,'factors':levels,'visibility_m':visibility,'visibility_source':vis_source if visibility is not None else '缺失',
            'incomplete':any(value is None for value in levels.values()),'source':'推断'}


def analyze_route(segments, departure, *, offline=False, spacing_m=None):
    """对真实路由采样并对齐天气；超出快照时间范围时明确报错。"""
    from .weather import fetch_weather
    samples = sample_route(segments, departure, spacing_m=spacing_m)
    forecasts = fetch_weather([(s['position'][1], s['position'][0]) for s in samples], offline=offline)
    results = []
    for sample, forecast in zip(samples, forecasts):
        passage = datetime.fromisoformat(sample['passage_utc'])
        weather = align_weather(passage, forecast['weather']['hourly'])
        source = {k: v for k, v in forecast.items() if k != 'weather'}
        results.append({**sample, 'weather': weather, 'weather_source': source, 'risk': classify_risk(weather)})
    return results
