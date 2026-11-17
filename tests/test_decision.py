from datetime import datetime, timedelta, timezone
import pytest
from app.decision import calculate_cost, evaluate_routes

PLAN=datetime(2025,1,1,8,tzinfo=timezone.utc)
REFERENCE=PLAN-timedelta(hours=4)


def route(distance,duration):
    return {'geometry':{'type':'LineString','coordinates':[[114,30],[114.1,30.1]]},'distance':distance,'duration':duration}


def sample_routes():
    return [{'id':'fast','segments':[route(120000,7200)]},{'id':'cheap','segments':[route(100000,18000)]}]


def forecast(points,*,offline):
    hours=[(datetime(2025,1,1,tzinfo=timezone.utc)+timedelta(hours=i)).strftime('%Y-%m-%dT%H:%M') for i in range(48)]
    hourly={'time':hours,'temperature_2m':[10]*48,'precipitation':[0]*48,'weather_code':[0]*48,'wind_speed_10m':[0]*48,'visibility':[10000]*48}
    return [{'mode':'fixture','source':'测试数据','retrieved_at_utc':'2025-01-01T00:00:00+00:00','data_kind':'test','weather':{'hourly':hourly}} for _ in points]


def test_cost_uses_weather_risk_lateness_and_simulated_parameters():
    assumptions={'preference_weight_floor':0.5,'freight_yuan_per_km':7,'time_cost_yuan_per_hour':80,'late_penalty_yuan':300,'warehouse_yuan_per_hour':40,'delay_probability_by_level':[0,.1,.2,.4,.7],'risk_penalty_yuan_by_level':[0,10,20,30,40],'cargo_risk_multiplier':{'普货':1},'unconfirmed_closure_probability':0.4,'unconfirmed_closure_penalty_yuan':50}
    out=calculate_cost(distance_km=100,duration_h=2,risk_level=2,promised_hours=3,cargo='普货',money_preference=0.5,time_preference=0.5,assumptions=assumptions)
    assert out['distance_cost']==700 and out['time_cost']==160
    assert out['delay_probability']==0.2 and out['expected_delay_cost']==60
    assert out['risk_penalty']==20
    assert out['expected_cost']==940


def test_preferences_change_route_ranking():
    fast=evaluate_routes(sample_routes(),PLAN,reference_time=REFERENCE,promised_hours=100,money_preference=0,time_preference=1,weather_fetcher=forecast)
    cheap=evaluate_routes(sample_routes(),PLAN,reference_time=REFERENCE,promised_hours=100,money_preference=1,time_preference=0,weather_fetcher=forecast)
    assert fast['decision']['route_id']=='fast'
    assert cheap['decision']['route_id']=='cheap'
    assert 0 <= fast['decision']['score'] <= 100
    assert len(fast['decision']['reasons'])==3


def test_confirmed_closure_excludes_candidate_and_unconfirmed_does_not():
    scene={'name':'模拟','inject':[{'edge':'E1','kind':'closed','start_h':-10,'end_h':10,'confirmed':True}]}
    result=evaluate_routes([sample_routes()[0]],PLAN,reference_time=REFERENCE,promised_hours=100,scenario=scene,weather_fetcher=forecast)
    assert result['decision'] is None
    assert all(c['status']=='closed' for c in result['candidates'])
    scene['inject'][0]['confirmed']=False
    result=evaluate_routes([sample_routes()[0]],PLAN,reference_time=REFERENCE,promised_hours=100,scenario=scene,weather_fetcher=forecast)
    assert result['decision'] is not None
    assert result['decision']['has_unconfirmed_closure'] is True


def test_slow_event_changes_travel_time_and_weather_alignment():
    r=[{'id':'only','segments':[route(20000,3600)]}]
    scene={'name':'模拟','inject':[{'edge':'E1','kind':'slow','start_h':-10,'end_h':10,'confirmed':False,'value':0.5}]}
    result=evaluate_routes(r,PLAN,reference_time=REFERENCE,promised_hours=100,scenario=scene,weather_fetcher=forecast)
    row=next(c for c in result['candidates'] if c['shift_hours']==0)
    assert row['duration_h']==pytest.approx(2)
    assert row['samples'][-1]['elapsed_seconds']==pytest.approx(7200)
    assert row['samples'][-1]['weather']['forecast_time_utc']=='2025-01-01T10:00:00+00:00'


def test_elapsed_time_window_and_past_departures():
    r=[{'id':'only','segments':[route(20000,3600)]}]
    scene={'name':'模拟','inject':[{'edge':'E1','kind':'slow','start_h':0.5,'end_h':1,'confirmed':False,'value':0.5}]}
    result=evaluate_routes(r,PLAN,reference_time=PLAN,promised_hours=100,scenario=scene,weather_fetcher=forecast)
    assert [x['status'] for x in result['candidates'][:3]]==['past']*3
    row=result['candidates'][3]
    assert row['duration_h']==pytest.approx(1.25)
    assert result['decision']['shift_hours']==0


def test_all_equal_zero_cost_has_finite_scores():
    assumptions={'preference_weight_floor':0.5,'promised_hours_default':12,'preference_default':0.5,'storage_hours_default':0,'freight_yuan_per_km':0,'time_cost_yuan_per_hour':0,'late_penalty_yuan':0,'warehouse_yuan_per_hour':0,'delay_probability_by_level':[0]*5,'risk_penalty_yuan_by_level':[0]*5,'cargo_risk_multiplier':{'普货':1},'unconfirmed_closure_probability':0,'unconfirmed_closure_penalty_yuan':0}
    result=evaluate_routes([sample_routes()[0]],PLAN,reference_time=REFERENCE,promised_hours=100,weather_fetcher=forecast,assumptions=assumptions)
    assert all(c['score']==100 for c in result['candidates'])
    assert result['decision']['shift_hours']==0


def test_route_specific_event_does_not_modify_other_routes():
    r=[{'id':'A','segments':[route(20000,3600)]},{'id':'B','segments':[route(20000,3600)]}]
    scene={'name':'模拟','inject':[{'edge':'E1','route_id':'A','kind':'slow','start_h':-10,'end_h':10,'confirmed':False,'value':0.5}]}
    result=evaluate_routes(r,PLAN,reference_time=REFERENCE,promised_hours=100,scenario=scene,weather_fetcher=forecast)
    by_id={c['route_id']:c for c in result['candidates'] if c['shift_hours']==0}
    assert by_id['A']['duration_h']==pytest.approx(2)
    assert by_id['B']['duration_h']==pytest.approx(1)


def test_closure_starting_while_on_edge_excludes_option():
    r=[{'id':'only','segments':[route(20000,3600)]}]
    scene={'name':'模拟','inject':[{'edge':'E1','kind':'closed','start_h':0.5,'end_h':2,'confirmed':True}]}
    result=evaluate_routes(r,PLAN,reference_time=PLAN,promised_hours=100,scenario=scene,weather_fetcher=forecast)
    assert result['candidates'][-1]['status']=='closed'
    assert result['decision'] is None


def test_real_fixtures_allow_weight_reordering_under_labeled_slowdown():
    from app.routing import get_route
    from app.scenarios import load_scenario
    raw=get_route((30.59,114.3),(26.89,112.57),offline=True)['response']['routes']
    routes=[{'id':'A','segments':[raw[0]]},{'id':'B','segments':[raw[1]]}]
    scenario=load_scenario('scenarios/preference_comparison.yaml')
    fast=evaluate_routes(routes,PLAN,reference_time=REFERENCE,promised_hours=12,scenario=scenario,offline=True,money_preference=0,time_preference=1)
    cheap=evaluate_routes(routes,PLAN,reference_time=REFERENCE,promised_hours=12,scenario=scenario,offline=True,money_preference=1,time_preference=0)
    assert fast['decision']['route_id']=='B'
    assert cheap['decision']['route_id']=='A'
    assert any(e['source']=='模拟' for c in cheap['candidates'] if c['status']=='available' for e in c['events'])
    assert fast['decision']['score'] != cheap['decision']['score']


def test_outside_weather_range_is_not_recommended():
    late_plan=PLAN+timedelta(days=8)
    result=evaluate_routes(sample_routes(),late_plan,reference_time=late_plan-timedelta(hours=4),promised_hours=100,weather_fetcher=forecast)
    assert result['decision'] is None
    assert all(c['status']=='weather_unavailable' for c in result['candidates'])


def test_known_late_arrival_has_certain_late_penalty():
    from app.decision import load_assumptions
    result=calculate_cost(distance_km=1,duration_h=3,risk_level=0,promised_hours=2,cargo='普货',money_preference=0.5,time_preference=0.5,assumptions=load_assumptions())
    assert result['delay_probability']==1
    assert result['expected_delay_cost']==load_assumptions()['late_penalty_yuan']


def test_each_ranked_route_has_its_own_explanation_and_trigger():
    result=evaluate_routes(sample_routes(),PLAN,reference_time=REFERENCE,promised_hours=100,weather_fetcher=forecast)
    assert all(row['reason'] and row['trigger'] for row in result['ranked_routes'])
    assert all(row['alternative_route_id'] != row['route_id'] for row in result['ranked_routes'])


def test_decision_exposes_when_arrival_misses_promised_deadline():
    routes=[{'id':'only','segments':[route(20000,4*3600)]}]
    result=evaluate_routes(routes,PLAN,reference_time=PLAN,promised_hours=2,weather_fetcher=forecast)
    decision=result['decision']
    assert decision['misses_promise'] is True
    assert decision['late_hours']==pytest.approx(2)
