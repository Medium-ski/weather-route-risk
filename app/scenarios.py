"""模拟事件仅作用于指定采样区间及相对发车时间窗口。"""
import re
from pathlib import Path
import yaml


def load_scenario(path):
    scenario=yaml.safe_load(Path(path).read_text(encoding='utf-8'))
    if not isinstance(scenario,dict) or not isinstance(scenario.get('name'),str) or not isinstance(scenario.get('inject'),list):
        raise ValueError('无效场景')
    for event in scenario['inject']:
        if not isinstance(event,dict) or not re.fullmatch(r'E[1-9]\d*',str(event.get('edge',''))) or event.get('kind') not in ('closed','slow'):
            raise ValueError('无效场景事件')
        if 'route_id' in event and (not isinstance(event['route_id'],str) or not event['route_id']): raise ValueError('路线标识无效')
        start,end=event.get('start_h'),event.get('end_h')
        if not isinstance(start,(int,float)) or not isinstance(end,(int,float)) or start >= end:
            raise ValueError('场景时间范围无效')
        if 'confirmed' in event and not isinstance(event['confirmed'],bool): raise ValueError('confirmed 必须为布尔值')
        event.setdefault('confirmed',False)
        if event['kind']=='slow' and (not isinstance(event.get('value'),(int,float)) or not 0 < event['value'] <= 1):
            raise ValueError('减速值必须是 0 到 1 之间的速度比例')
    return scenario


def apply_scenario(samples, scenario, *, route_id=None):
    result=[[] for _ in range(max(0,len(samples)-1))]
    for event in scenario['inject']:
        if 'route_id' in event and event['route_id'] != route_id: continue
        index=int(event['edge'][1:])-1
        if index >= len(result): continue
        a,b=samples[index]['elapsed_seconds']/3600,samples[index+1]['elapsed_seconds']/3600
        if b > event['start_h'] and a < event['end_h']:
            result[index].append({**event,'source':'模拟'})
    return result
