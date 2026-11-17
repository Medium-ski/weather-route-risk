from pathlib import Path
import pytest
from app.scenarios import load_scenario, apply_scenario


def test_injection_only_within_time_window_and_retains_simulation_label(tmp_path):
    f=tmp_path/'case.yaml'
    f.write_text('name: 雪\ninject:\n  - {edge: E1, kind: closed, start_h: 1, end_h: 2, confirmed: true}\n  - {edge: E2, kind: slow, value: 0.55, start_h: 5, end_h: 6, confirmed: false}\n')
    scenario=load_scenario(f)
    intervals=apply_scenario([{'elapsed_seconds':3600},{'elapsed_seconds':5400},{'elapsed_seconds':7200}],scenario)
    assert intervals[0][0]['confirmed'] is True
    assert intervals[0][0]['source']=='模拟'
    assert intervals[1]==[]


def test_closed_requires_explicit_confirmation(tmp_path):
    f=tmp_path/'case.yaml'; f.write_text('name: 雪\ninject:\n  - {edge: E1, kind: closed, start_h: 0, end_h: 1}\n')
    event=load_scenario(f)['inject'][0]
    assert event['confirmed'] is False


def test_invalid_slow_value_rejected(tmp_path):
    f=tmp_path/'case.yaml'; f.write_text('name: 雪\ninject:\n  - {edge: E1, kind: slow, start_h: 0, end_h: 1, value: 1.5}\n')
    with pytest.raises(ValueError): load_scenario(f)


def test_route_specific_events_are_not_applied_to_other_route(tmp_path):
    f=tmp_path/'case.yaml'; f.write_text('name: 模拟\ninject:\n  - {edge: E1, route_id: A, kind: slow, value: 0.5, start_h: 0, end_h: 1}\n')
    scenario=load_scenario(f)
    samples=[{'elapsed_seconds':0},{'elapsed_seconds':1800}]
    assert apply_scenario(samples,scenario,route_id='B')==[[]]
    assert len(apply_scenario(samples,scenario,route_id='A')[0])==1
