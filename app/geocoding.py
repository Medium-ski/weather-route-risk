"""离线内置坐标与在线地点查询；不把同名地点静默当作同一地点。"""
from datetime import datetime, timezone
import logging
import math
import os
from pathlib import Path
import re
from time import monotonic
import httpx
import yaml

ROOT=Path(__file__).resolve().parent.parent
URL='https://geocoding-api.open-meteo.com/v1/search'
SOURCE='Open-Meteo Geocoding / GeoNames'
logger=logging.getLogger(__name__)
_CACHE={}


def _fetch(query):
    cached=_CACHE.get(query)
    if cached and monotonic()-cached[0] < float(os.getenv('CACHE_TTL_MIN','30'))*60:
        return cached[1]
    params={'name':query,'count':10,'language':'zh','format':'json'}
    with httpx.Client(timeout=5.0) as client:
        for _ in range(2):
            started=monotonic(); status='连接失败'
            try:
                response=client.get(URL,params=params); status=str(response.status_code); response.raise_for_status()
                payload=response.json()
                if not isinstance(payload,dict) or not isinstance(payload.get('results',[]),list):
                    raise ValueError('地点服务返回格式不正确')
                result={'results':payload.get('results',[]),'source':SOURCE,'source_url':str(response.request.url),
                        'retrieved_at_utc':datetime.now(timezone.utc).isoformat()}
                if len(_CACHE)>=128: _CACHE.pop(next(iter(_CACHE)))
                _CACHE[query]=(monotonic(),result)
                return result
            except (httpx.HTTPError,ValueError) as exc:
                logger.warning('地点查询失败: %s',exc)
            finally:
                logger.info('地点查询 URL=%s 耗时=%.3fs 状态=%s',URL,monotonic()-started,status)
    raise ValueError('地点查询服务暂不可用，请重试或输入纬度,经度')


def _base_name(text):
    return text[:-1] if text.endswith('市') and len(text)>2 else text


def _format_label(result):
    components=[]
    for key in ('admin1','admin2','country'):
        part=result.get(key)
        if part and part not in components: components.append(part)
    return result['name'] + ('（'+' · '.join(components)+'）' if components else '')


def search_places(query, *, search=None):
    name=_base_name(query.strip())
    if not 2<=len(name)<=100: return []
    data=(search or _fetch)(name)
    results=[]
    for record in data['results']:
        try:
            lat,lon=float(record['latitude']),float(record['longitude'])
            if not (-90<=lat<=90 and -180<=lon<=180 and math.isfinite(lat) and math.isfinite(lon)) or not isinstance(record['name'],str): continue
        except (KeyError,TypeError,ValueError): continue
        results.append({'label':_format_label(record),'name':record['name'],
                        'position':(lat,lon),'feature_code':record.get('feature_code',''),
                        'source':data['source'],'source_url':data['source_url'],
                        'retrieved_at_utc':data['retrieved_at_utc']})
    return results


def resolve_place(text, *, offline=False, search=None):
    name=text.strip()
    if not name: raise ValueError('地点不能为空')
    cities=yaml.safe_load((ROOT/'config/cities.yaml').read_text(encoding='utf-8'))
    if name in cities:
        return {'input':name,'label':name,'position':tuple(cities[name]),'source':'任务给定的城市坐标表',
                'source_url':None,'retrieved_at_utc':None,'source_type':'用户提供'}
    match=re.fullmatch(r'\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*,\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*',name)
    if match:
        lat,lon=map(float,match.groups())
        if not (-90<=lat<=90 and -180<=lon<=180): raise ValueError('纬度或经度超出有效范围')
        return {'input':name,'label':name,'position':(lat,lon),'source':'用户输入的经纬度',
                'source_url':None,'retrieved_at_utc':None,'source_type':'用户输入'}
    if offline: raise ValueError(f'离线模式无法查询“{name}”；请选择内置城市或输入纬度,经度，并确保路线已缓存')
    qualified=re.fullmatch(r'(.+?)（(.+)）',name)
    query=qualified.group(1) if qualified else name
    choices=search_places(query,search=search)
    exact=[c for c in choices if _base_name(c['name']).casefold()==_base_name(query).casefold()]
    if qualified:
        exact=[c for c in exact if c['label']==name]
    elif len(exact)>1:
        principal=[c for c in exact if c['feature_code'] in ('PPLC','PPLA')]
        if len(principal)==1: exact=principal
    if not exact:
        raise ValueError(f'未找到地点“{name}”，请从建议中选择或输入纬度,经度')
    if len(exact)>1:
        raise ValueError(f'“{name}”有多个同名地点，请从建议中选择具体地区：'+ '；'.join(c['label'] for c in exact[:5]))
    return {'input':name,**exact[0],'source_type':'真实'}
