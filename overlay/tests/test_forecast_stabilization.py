import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'infra'/'budget_ledger'))
from auto_forecast import add_demand

def test_source_id_merge_is_idempotent():
    s={'dates':{}}
    assert add_demand(s,'2026-08-25','teacher',1,2,1.2,'job:one') is True
    assert add_demand(s,'2026-08-25','teacher',1,2,1.2,'job:one') is False
    i=s['dates']['2026-08-25']['teacher']
    assert i['jobs']==1 and i['units']==2 and i['expected_cost_usd']==1.2

def test_no_duplicate_pacing_env_keys():
    text=(ROOT/'.github/workflows/budgeted-unified-job.yml').read_text()
    reserve=text.split('\n  reserve:\n',1)[1].split('\n  launch:\n',1)[0]
    for key in ['GPU_BUDGET_PACING_ENABLED:','GPU_BUDGET_PACING_MODE:','GPU_BUDGET_PACING_MULTIPLIER:','GPU_BUDGET_PACING_MIN_DAILY_USD:','GPU_BUDGET_PACING_MAX_DAILY_USD:']:
        assert reserve.count(key)==1

def test_failure_mode_env_is_exposed():
    text=(ROOT/'.github/workflows/budgeted-unified-job.yml').read_text()
    assert 'GPU_BUDGET_FORECAST_ACTIONS_FAILURE_MODE' in text
