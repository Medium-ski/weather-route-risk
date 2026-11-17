"""使用可追溯模拟假设比较真实路线和发车时间。"""
from datetime import datetime, timedelta, timezone
from math import isfinite
from pathlib import Path
import yaml
from .analysis import sample_route, align_weather, classify_risk
from .weather import fetch_weather, WeatherUnavailable

ROOT=Path(__file__).resolve().parent.parent


def load_assumptions():
    data=yaml.safe_load((ROOT/'config'/'assumptions.yaml').read_text(encoding='utf-8'))
    return {key:item['value'] for key,item in data.items()}


def calculate_cost(*, distance_km, duration_h, risk_level, promised_hours, cargo,
                   money_preference, time_preference, assumptions, delivery_elapsed_h=None,
                   storage_hours=0, has_unconfirmed_closure=False):
    """返回模拟参数与推断结果；偏好是主观权重，非实际报价。"""
    if any(not isinstance(x,(int,float)) or not isfinite(x) for x in (distance_km,duration_h,promised_hours,money_preference,time_preference,storage_hours)):
        raise ValueError('成本输入必须为有限数字')
    if distance_km<0 or duration_h<0 or promised_hours<=0 or storage_hours<0 or not 0<=money_preference<=1 or not 0<=time_preference<=1:
        raise ValueError('成本输入超出范围')
    if risk_level not in range(5) or cargo not in assumptions['cargo_risk_multiplier']:
        raise ValueError('未知风险等级或货类')
    arrival = duration_h if delivery_elapsed_h is None else delivery_elapsed_h
    if not isinstance(arrival,(int,float)) or not isfinite(arrival): raise ValueError('无效到达时间')
    probability=assumptions['delay_probability_by_level'][risk_level]
    if has_unconfirmed_closure: probability=max(probability,assumptions['unconfirmed_closure_probability'])
    if arrival > promised_hours: probability=1.0
    if not 0 <= probability <= 1: raise ValueError('模拟延误概率无效')
    distance_cost=distance_km*assumptions['freight_yuan_per_km']
    time_cost=duration_h*assumptions['time_cost_yuan_per_hour']
    storage_cost=storage_hours*assumptions['warehouse_yuan_per_hour']
    expected_delay_cost=probability*assumptions['late_penalty_yuan']
    risk_penalty=assumptions['risk_penalty_yuan_by_level'][risk_level]*assumptions['cargo_risk_multiplier'][cargo]
    if has_unconfirmed_closure: risk_penalty+=assumptions['unconfirmed_closure_penalty_yuan']
    floor=assumptions['preference_weight_floor']
    cost=(floor+money_preference)*(distance_cost+storage_cost+expected_delay_cost)+(floor+time_preference)*time_cost+risk_penalty
    if not isfinite(cost) or cost < 0: raise ValueError('模拟成本无效')
    return {'distance_cost':distance_cost,'time_cost':time_cost,'storage_cost':storage_cost,
            'delay_probability':probability,'expected_delay_cost':expected_delay_cost,
            'risk_penalty':risk_penalty,'expected_cost':cost,'source':'推断',
            'probability_source':'模拟参数与推断'}


def _timing(samples, shift, scenario, route_id):
    """事件以原计划发车时刻为零点，在每个区间内按事件边界分段计算。"""
    events=scenario['inject'] if scenario else []
    current=shift*3600.0
    times=[current]; applied=[]
    for index,(left,right) in enumerate(zip(samples,samples[1:]),1):
        remaining=right['elapsed_seconds']-left['elapsed_seconds']
        edge_events=[e for e in events if e['edge']==f'E{index}' and ('route_id' not in e or e['route_id']==route_id)]
        while remaining > 1e-8:
            active=[e for e in edge_events if e['start_h']*3600 <= current < e['end_h']*3600]
            for e in active:
                marked={**e,'source':'模拟'}
                if marked not in applied: applied.append(marked)
            if any(e['kind']=='closed' and e['confirmed'] for e in active):
                return None, applied, f'E{index}'
            speed=min((e['value'] for e in active if e['kind']=='slow'),default=1.0)
            boundaries=[h*3600 for e in edge_events for h in (e['start_h'],e['end_h']) if h*3600>current+1e-8]
            available=min(boundaries)-current if boundaries else float('inf')
            duration=min(remaining/speed,available)
            remaining=max(0.0,remaining-duration*speed)
            current+=duration
        times.append(current)
    return times,applied,None


def evaluate_routes(routes, planned_departure, *, reference_time=None, promised_hours=None, cargo='普货',
                    money_preference=None,time_preference=None,storage_hours=None,scenario=None,
                    offline=False,weather_fetcher=fetch_weather,assumptions=None):
    """计算每条路线上 -3/-2/-1/0 小时的可行性、成本与排名。"""
    if planned_departure.tzinfo is None or planned_departure.utcoffset() is None: raise ValueError('计划发车时间必须带时区')
    plan=planned_departure.astimezone(timezone.utc)
    reference=reference_time or datetime.now(timezone.utc)
    if reference.tzinfo is None or reference.utcoffset() is None: raise ValueError('参考时间必须带时区')
    reference=reference.astimezone(timezone.utc)
    a=load_assumptions() if assumptions is None else assumptions
    promised_hours=a['promised_hours_default'] if promised_hours is None else promised_hours
    money_preference=a['preference_default'] if money_preference is None else money_preference
    time_preference=a['preference_default'] if time_preference is None else time_preference
    storage_hours=a['storage_hours_default'] if storage_hours is None else storage_hours
    if not routes: raise ValueError('没有待分析路线')
    if len({route['id'] for route in routes}) != len(routes): raise ValueError('路线标识重复')
    # Validate shared user inputs even if every candidate is unavailable.
    calculate_cost(distance_km=0,duration_h=0,risk_level=0,promised_hours=promised_hours,cargo=cargo,
                   money_preference=money_preference,time_preference=time_preference,assumptions=a,storage_hours=storage_hours)
    candidates=[]
    for route in routes:
        samples=sample_route(route['segments'],plan)
        points=[(s['position'][1],s['position'][0]) for s in samples]
        try:
            forecasts=weather_fetcher(points,offline=offline)
            if len(forecasts)!=len(samples): raise WeatherUnavailable('天气数据数量不匹配')
            weather_error=None
        except (WeatherUnavailable,ValueError) as exc:
            forecasts=None; weather_error=str(exc)
        for shift in (-3,-2,-1,0):
            depart=plan+timedelta(hours=shift)
            row={'route_id':route['id'],'shift_hours':shift,'departure_utc':depart.isoformat(),
                 'distance_km':samples[-1]['distance_m']/1000,'source':'推断',
                 'route_provenance':route.get('provenance')}
            candidates.append(row)
            if depart < reference:
                row.update(status='past',reason='发车时间已过去'); continue
            if weather_error:
                row.update(status='weather_unavailable',reason=weather_error); continue
            times,events,closed_edge=_timing(samples,shift,scenario,route['id'])
            if closed_edge:
                row.update(status='closed',reason=f'{closed_edge} 存在模拟已确认封路',events=events); continue
            analyzed=[]
            try:
                for sample,seconds,forecast in zip(samples,times,forecasts):
                    at=plan+timedelta(seconds=seconds)
                    weather=align_weather(at,forecast['weather']['hourly'])
                    risk=classify_risk(weather)
                    if risk['incomplete']: raise ValueError('天气数据不完整，无法可靠评估风险')
                    analyzed.append({**sample,'elapsed_seconds':seconds-times[0],'passage_utc':at.isoformat(),'weather':weather,'risk':risk,
                                     'weather_source':{k:v for k,v in forecast.items() if k!='weather'}})
            except (ValueError,KeyError,TypeError) as exc:
                row.update(status='weather_unavailable',reason=str(exc)); continue
            max_risk=max(item['risk']['level'] for item in analyzed)
            duration=(times[-1]-times[0])/3600
            uncertain=any(e['kind']=='closed' and not e['confirmed'] for e in events)
            costs=calculate_cost(distance_km=row['distance_km'],duration_h=duration,risk_level=max_risk,
                     promised_hours=promised_hours,cargo=cargo,money_preference=money_preference,
                     time_preference=time_preference,assumptions=a,delivery_elapsed_h=times[-1]/3600,
                     storage_hours=storage_hours,has_unconfirmed_closure=uncertain)
            late_hours=max(0.0,times[-1]/3600-promised_hours)
            row.update(status='available',arrival_utc=(plan+timedelta(seconds=times[-1])).isoformat(),
                       misses_promise=late_hours>0,late_hours=late_hours,
                       duration_h=duration,highest_risk=max_risk,has_unconfirmed_closure=uncertain,
                       events=events,samples=analyzed,cost=costs)
    eligible=[c for c in candidates if c['status']=='available']
    if not eligible: return {'candidates':candidates,'ranked_routes':[],'decision':None,'source':'推断'}
    worst=max(c['cost']['expected_cost'] for c in eligible)
    for row in eligible:
        row['score']=100.0 if worst==0 else max(0.0,min(100.0,100*(1-row['cost']['expected_cost']/worst)))
    best_by_route=[]
    for route in routes:
        options=[c for c in eligible if c['route_id']==route['id']]
        if options: best_by_route.append(min(options,key=lambda c:(c['cost']['expected_cost'],abs(c['shift_hours']))))
    best_by_route.sort(key=lambda c:(c['cost']['expected_cost'],abs(c['shift_hours'])))
    for row in best_by_route:
        highest_index=max(range(len(row['samples'])),key=lambda i:row['samples'][i]['risk']['level'])
        edge=f'E{min(highest_index+1,max(1,len(row["samples"])-1))}'
        alternative=next((other['route_id'] for other in best_by_route if other['route_id']!=row['route_id']),None)
        condition='维持橙色及以上' if row['highest_risk']>=3 else '升至橙色或以上'
        trigger=f'若 {edge} 风险{condition}或出现已确认封路，重新计算所有可行方案'
        if alternative is not None: trigger+=f'，并核查路线 {alternative} 是否可通行'
        row['reason']=(f'当前假设下预期成本 {row["cost"]["expected_cost"]:.2f} 元，'
                       f'预计运输 {row["duration_h"]:.2f} 小时，最高风险等级 {row["highest_risk"]}')
        row['trigger']=trigger
        row['alternative_route_id']=alternative
    winner=best_by_route[0]
    reasons=[f'在当前权重和假设下，预期成本为 {winner["cost"]["expected_cost"]:.2f} 元，属于可行方案中最低',
             f'路线最高天气风险等级为 {winner["highest_risk"]}，按经过时间匹配逐小时预报',
             f'预计运输 {winner["duration_h"]:.2f} 小时，预计到达 {winner["arrival_utc"]}']
    decision={**winner,'reasons':reasons}
    return {'candidates':candidates,'ranked_routes':best_by_route,'decision':decision,'source':'推断'}
