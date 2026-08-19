import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"infra"/"budget_ledger"))
from auto_forecast_stabilized import add_demand, confidence_summary

def test_source_merge_is_idempotent():
    s={"dates":{}}
    assert add_demand(s,"2026-08-25","teacher",1,2,1.2,"job:a")
    assert not add_demand(s,"2026-08-25","teacher",1,2,1.2,"job:a")

def test_health():
    d={"actions":{"failed_queries":1,"successful_queries":4}}
    assert confidence_summary(d,True)==("degraded","medium")
