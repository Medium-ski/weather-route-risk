"""本机单站点 API，所有决策由服务端计算。"""
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path
from time import monotonic
from typing import Literal
import json
import logging
import os
import yaml
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
from .analysis import _distance, sample_route
from .decision import evaluate_routes, load_assumptions
from .route_parser import parse_route, route_segments
from .routing import get_route, RouteUnavailable
from .scenarios import load_scenario
from .geocoding import resolve_place, search_places
from .weather import WeatherUnavailable

ROOT=Path(__file__).resolve().parent.parent
REPORTS_DIR=ROOT/'reports'
envfile=ROOT/'.env'
if envfile.exists():
    for line in envfile.read_text(encoding='utf-8').splitlines():
        key,sep,value=line.strip().partition('=')
        if sep and key in ('ROUTER_MODE','CACHE_TTL_MIN'):
            os.environ.setdefault(key,value.strip())
app=FastAPI(title='运输路线天气风险预警')
app.mount('/static', StaticFiles(directory=ROOT/'static'), name='static')
logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(name)s %(message)s')
_ROUTE_CACHE={}


class Request(BaseModel):
    mode: Literal['live','offline','scenario']='live'
    business_mode: Literal['plan','inspect']='plan'
    origin: str=Field(default='武汉',max_length=100)
    destination: str=Field(default='衡阳',max_length=100)
    route_text: str=Field(default='',max_length=50000)
    departure_utc: datetime
    cargo: Literal['普货','冷链','高值']='普货'
    promised_hours: float=Field(default=12,gt=0,le=1000)
    time_preference: float=Field(default=0.5,ge=0,le=1)
    money_preference: float=Field(default=0.5,ge=0,le=1)
    scenario: Literal['none','closure','preference']='none'

    @field_validator('departure_utc')
    @classmethod
    def aware(cls,value):
        if value.tzinfo is None or value.utcoffset() is None: raise ValueError('发车时间必须包含时区')
        return value.astimezone(timezone.utc)


def _cached_route(start,end,*,offline=False):
    key=(tuple(start),tuple(end),offline)
    entry=_ROUTE_CACHE.get(key)
    if entry and monotonic()-entry[0]<float(os.getenv('CACHE_TTL_MIN','30'))*60: return entry[1]
    result=get_route(start,end,offline=offline)
    if len(_ROUTE_CACHE)>=64: _ROUTE_CACHE.pop(next(iter(_ROUTE_CACHE)))
    _ROUTE_CACHE[key]=(monotonic(),result)
    return result


def _point(text, *, offline=False):
    return resolve_place(text,offline=offline)['position']


def _cities_near(segments):
    cities=yaml.safe_load((ROOT/'config/cities.yaml').read_text(encoding='utf-8'))
    limit=load_assumptions()['nearby_city_radius_km']*1000
    coords=[p for segment in segments for p in segment['geometry']['coordinates']]
    return [name for name,(lat,lon) in cities.items() if any(_distance([lon,lat],p)<=limit for p in coords)]


def analyze(request):
    offline=request.mode=='offline'
    resolved=[]
    def resolve(name):
        place=resolve_place(name,offline=offline)
        resolved.append(place)
        return place['position']
    if request.business_mode=='plan':
        start,end=resolve(request.origin),resolve(request.destination)
        routed=_cached_route(start,end,offline=offline)
        provenance={k:routed[k] for k in ('source','source_url','retrieved_at_utc','mode')}
        routes=[{'id':chr(65+i),'segments':[route],'provenance':[provenance]} for i,route in enumerate(routed['response']['routes'][:3])]
    else:
        points=parse_route(request.route_text,resolver=resolve)
        legs=route_segments(points,offline=offline,router=_cached_route)
        provenance=[{k:leg[k] for k in ('source','source_url','retrieved_at_utc','mode')} for leg in legs]
        routes=[{'id':'A','segments':legs,'provenance':provenance}]
    scene_name=request.scenario
    if request.mode=='scenario' and scene_name=='none': scene_name='closure'
    paths={'closure':'snow_closure.yaml','preference':'preference_comparison.yaml'}
    scenario=load_scenario(ROOT/'scenarios'/paths[scene_name]) if scene_name!='none' else None
    # Historical fixture dates are a controlled simulation, never current time.
    reference=request.departure_utc-timedelta(hours=4) if offline else datetime.now(timezone.utc)
    result=evaluate_routes(routes,request.departure_utc,reference_time=reference,
        promised_hours=request.promised_hours,cargo=request.cargo,
        time_preference=request.time_preference,money_preference=request.money_preference,
        scenario=scenario,offline=offline)
    geometry=[]
    for route in routes:
        segments=[segment.get('route',segment) for segment in route['segments']]
        geometry.append({'id':route['id'],'segments':segments,'provenance':route['provenance'],
                         'nearby_cities':_cities_near(segments),'preview_samples':sample_route(route['segments'],request.departure_utc)})
    return {'mode':request.mode,'reference_kind':'模拟参考时刻' if offline else '实际参考时刻',
            'reference_utc':reference.isoformat(),'scenario':scenario,'resolved_places':resolved,'routes':geometry,'result':result}


def safe_analyze(request):
    try: return analyze(request)
    except (ValueError,RouteUnavailable,WeatherUnavailable) as exc:
        raise HTTPException(status_code=400,detail=str(exc)) from exc


@app.get('/')
def index(): return FileResponse(ROOT/'static/index.html')


@app.get('/api/config')
def config():
    return {'cities':yaml.safe_load((ROOT/'config/cities.yaml').read_text(encoding='utf-8')),
            'assumptions':yaml.safe_load((ROOT/'config/assumptions.yaml').read_text(encoding='utf-8'))}


@app.get('/api/places')
def api_places(query:str):
    if not 2<=len(query.strip())<=100: return {'places':[]}
    try: return {'places':search_places(query)}
    except ValueError as exc: raise HTTPException(status_code=503,detail=str(exc)) from exc


@app.post('/api/analyze')
def api_analyze(request:Request): return safe_analyze(request)


def _display(value):
    if isinstance(value,(dict,list)): return escape(json.dumps(value,ensure_ascii=False))
    return escape(str(value))


@app.post('/api/report')
def report(request:Request):
    data=safe_analyze(request); result=data['result']; decision=result['decision']
    if not decision: raise HTTPException(status_code=400,detail='当前没有可导出的可行决策')
    source=decision['samples'][0]['weather_source']
    assumptions=yaml.safe_load((ROOT/'config/assumptions.yaml').read_text(encoding='utf-8'))
    names={'sampling_interval_km':'采样间距','freight_yuan_per_km':'运价（元/km）','time_cost_yuan_per_hour':'时间成本（元/小时）','late_penalty_yuan':'延误赔付（元）','warehouse_yuan_per_hour':'仓储费（元/小时）','promised_hours_default':'默认承诺时效（小时）','delay_probability_by_level':'按风险等级的延误概率','risk_penalty_yuan_by_level':'按风险等级的风险惩罚（元）','cargo_risk_multiplier':'货类风险系数','unconfirmed_closure_probability':'模拟预报封路延误概率下限','unconfirmed_closure_penalty_yuan':'模拟预报封路风险惩罚（元）','preference_weight_floor':'偏好权重底数','preference_default':'默认偏好','storage_hours_default':'默认仓储时长（小时）','nearby_city_radius_km':'附近城市范围（km）'}
    rows=''.join(f'<tr><td>{escape(names.get(k,k))}</td><td>{_display(v["value"])} <small>模拟</small></td><td>{escape(v["reason"])}</td></tr>' for k,v in assumptions.items())
    reasons=''.join(f'<li>{escape(reason)} <small>推断</small></li>' for reason in decision['reasons'])
    overdue=f'<p><strong>预计超过承诺时效 {decision["late_hours"]:.1f} 小时</strong> <small>推断</small></p>' if decision['misses_promise'] else ''
    scen=f'<p>场景：{escape(data["scenario"]["name"])} <small>模拟</small>；事件数 {len(data["scenario"]["inject"])} <small>模拟</small></p>' if data['scenario'] else ''
    routes=''.join(f'<tr><td>{escape(str(r["route_id"]))}</td><td>{r["distance_km"]:.2f} km <small>真实</small></td><td>{r["duration_h"]:.2f} h <small>推断</small></td><td>{r["score"]:.2f} <small>推断</small></td><td>{r["cost"]["expected_cost"]:.2f} 元 <small>推断</small></td></tr>' for r in result['ranked_routes'])
    body=f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>运输路线决策报告</title><style>body{{font:16px/1.7 -apple-system,BlinkMacSystemFont,sans-serif;max-width:900px;margin:45px auto;color:#172b3d;padding:0 24px}}h1,h2{{color:#123744}}small{{border:1px solid #a9b8b5;border-radius:8px;padding:1px 5px;color:#286256}}table{{border-collapse:collapse;width:100%;margin:16px 0}}td,th{{border-bottom:1px solid #ddd;padding:9px;text-align:left;vertical-align:top}}.note{{padding:14px;background:#eef6f2}}</style><body><p>ROUTEWISE · 决策报告</p><h1>运输路线天气风险决策</h1><div class="note">{escape(data['reference_kind'])}：{escape(data['reference_utc'])} <small>{'模拟' if request.mode=='offline' else '真实'}</small><br>天气：{escape(source['source'])}，获取时间 {escape(source['retrieved_at_utc'])} <small>真实</small></div>{scen}<h2>建议方案</h2><p>路线 {escape(str(decision['route_id']))}，发车 {escape(decision['departure_utc'])} <small>推断</small>；预计到达 {escape(decision['arrival_utc'])} <small>推断</small></p><ol>{reasons}</ol>{overdue}<p>{escape(decision['trigger'])}</p><h2>路线比较</h2><table><tr><th>路线</th><th>里程</th><th>耗时</th><th>推荐指数</th><th>加权预期成本</th></tr>{routes}</table><h2>数据与假设</h2><p>地图与路由数据 © <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>，遵循 <a href="https://opendatacommons.org/licenses/odbl/1-0/">ODbL</a>；天气数据来自 <a href="https://open-meteo.com/">Open-Meteo</a>，地名数据来自 <a href="https://www.geonames.org/">GeoNames</a>，遵循 <a href="https://creativecommons.org/licenses/by/4.0/">CC BY 4.0</a>。数据经过采样、时间匹配及风险计算。</p><p>地点解析：{_display(data.get('resolved_places'))}。路由：{_display(decision.get('route_provenance'))} <small>真实</small>。天气：{escape(source['source'])} <small>真实</small>。风险与决策为规则推断，非官方预警或现实封路公告；费用、概率及场景均为模拟，不构成报价。</p><p>用户选择：货类 {escape(request.cargo)}，承诺时效 {request.promised_hours:g} 小时 <small>用户输入</small>，省钱偏好 {request.money_preference:g} <small>用户输入</small>，赶时间偏好 {request.time_preference:g} <small>用户输入</small>。</p><table><tr><th>参数</th><th>取值</th><th>理由</th></tr>{rows}</table></body></html>'''
    return HTMLResponse(body,headers={'Content-Disposition':'attachment; filename="transport-decision.html"'})


@app.post('/api/report/save')
def save_report(request:Request):
    page=report(request)
    REPORTS_DIR.mkdir(exist_ok=True)
    filename='decision-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'.html'
    with (REPORTS_DIR/filename).open('xb') as target:
        target.write(page.body)
    return {'filename':filename,'relative_path':'reports/'+filename,'url':'/reports/'+filename}


@app.get('/reports/{filename}')
def view_report(filename:str):
    path=REPORTS_DIR/filename
    if Path(filename).name!=filename or not filename.endswith('.html') or not path.is_file():
        raise HTTPException(status_code=404,detail='报告不存在')
    return FileResponse(path,media_type='text/html')
