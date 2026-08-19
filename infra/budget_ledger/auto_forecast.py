#!/usr/bin/env python3
from __future__ import annotations

import argparse
import glob
import json
import os
import urllib.parse
import urllib.request
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml
from zoneinfo import ZoneInfo

from config import load_config, resolved_forecast
from core import reservation_state
from forecast import load_schedule
from storage import load_events


def deep_get(obj, path):
    cur = obj
    for part in path.split('.'):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def parse_dt(value):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def load_obj(path):
    p = Path(path)
    try:
        with p.open('r', encoding='utf-8') as f:
            return json.load(f) if p.suffix.lower() == '.json' else (yaml.safe_load(f) or {})
    except Exception:
        return {}


def estimate_spec(spec, units_override, forecast_cfg):
    workload = spec.get('workload')
    if workload not in {'teacher', 'student'}:
        return None, 0.0, 0.0, 0.0

    meta = deep_get(spec, 'metadata.forecast') or {}
    expected = meta.get('expected_cost_usd')
    if expected is None:
        expected = deep_get(spec, 'budget.max_cost_usd')

    if units_override is not None:
        units = float(units_override)
    elif meta.get('units') is not None:
        units = float(meta['units'])
    elif workload == 'teacher':
        units = float(deep_get(spec, 'accounting.input_audio_hours') or 0.0)
    else:
        units = float(deep_get(spec, 'accounting.epochs') or 0.0)

    jobs = float(meta.get('jobs', 1.0) or 1.0)
    if expected is None:
        expected = (
            units * float(forecast_cfg['fallback_cost_per_unit_usd'].get(workload, 0.0))
            + jobs * float(forecast_cfg.get('fallback_cost_per_job_usd', {}).get(workload, 0.0))
        )
    return workload, jobs, units, max(0.0, float(expected))


def add_demand(schedule, day, workload, jobs, units, expected_cost_usd, source_id):
    item = schedule.setdefault('dates', {}).setdefault(day, {}).setdefault(workload, {})
    item['jobs'] = float(item.get('jobs', 0.0) or 0.0) + jobs
    item['units'] = float(item.get('units', 0.0) or 0.0) + units
    item['expected_cost_usd'] = float(item.get('expected_cost_usd', 0.0) or 0.0) + expected_cost_usd
    sources = item.setdefault('sources', [])
    if source_id not in sources:
        sources.append(source_id)


def github_runs(repo, token, status, per_page):
    query = urllib.parse.urlencode({'status': status, 'per_page': per_page})
    req = urllib.request.Request(
        f'https://api.github.com/repos/{repo}/actions/runs?{query}',
        headers={
            'Accept': 'application/vnd.github+json',
            'Authorization': f'Bearer {token}',
            'X-GitHub-Api-Version': '2026-03-10',
            'User-Agent': 'AudioAttention-Exp-budget-forecast',
        },
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.load(resp).get('workflow_runs', [])


def decode_budgeted_run(title, prefix):
    if not title.startswith(prefix):
        return None
    parts = title[len(prefix):].rsplit('|', 1)
    if len(parts) != 2:
        return None
    try:
        return parts[0], float(parts[1])
    except ValueError:
        return None


def workflow_schedules(data):
    trigger = data.get('on', data.get(True))
    if not isinstance(trigger, dict):
        return []
    value = trigger.get('schedule') or []
    return value if isinstance(value, list) else []


def collect_specs(schedule, source_cfg, forecast_cfg, now, horizon, tz_name):
    cfg = source_cfg.get('job_specs', {})
    if not cfg.get('enabled', True):
        return
    seen = set()
    tz = ZoneInfo(tz_name)
    for pattern in cfg.get('globs', []):
        for path in glob.glob(pattern, recursive=True):
            if path in seen:
                continue
            seen.add(path)
            spec = load_obj(path)
            when = None
            for field in cfg.get('schedule_fields', []):
                when = parse_dt(deep_get(spec, field))
                if when:
                    break
            if not when or when < now or when > horizon:
                continue
            workload, jobs, units, cost = estimate_spec(spec, None, forecast_cfg)
            if workload:
                add_demand(schedule, when.astimezone(tz).date().isoformat(), workload, jobs, units, cost, f'job-spec:{path}')


def collect_cron(schedule, source_cfg, forecast_cfg, now, horizon, tz_name):
    from croniter import croniter
    out_tz = ZoneInfo(tz_name)
    for path, rule in source_cfg.get('workflow_rules', {}).items():
        if not rule.get('include_schedule', False):
            continue
        for entry in workflow_schedules(load_obj(path)):
            expr = entry.get('cron') if isinstance(entry, dict) else None
            if not expr:
                continue
            cron_tz = timezone.utc
            if isinstance(entry, dict) and entry.get('timezone'):
                try:
                    cron_tz = ZoneInfo(str(entry['timezone']))
                except Exception:
                    pass
            iterator = croniter(str(expr), now.astimezone(cron_tz))
            while True:
                occurrence = iterator.get_next(datetime)
                if occurrence.tzinfo is None:
                    occurrence = occurrence.replace(tzinfo=cron_tz)
                if occurrence.astimezone(timezone.utc) > horizon:
                    break
                units = float(rule.get('units', 1.0))
                spec = {'workload': rule.get('workload'), 'metadata': {'forecast': {'jobs': 1.0, 'units': units}}}
                workload, jobs, units, cost = estimate_spec(spec, units, forecast_cfg)
                if workload:
                    add_demand(schedule, occurrence.astimezone(out_tz).date().isoformat(), workload, jobs, units, cost, f'cron:{path}:{expr}:{occurrence.isoformat()}')


def collect_runs(schedule, source_cfg, forecast_cfg, now, tz_name, repo, token, exclude_run_id, reserved_job_ids):
    cfg = source_cfg.get('actions', {})
    if not cfg.get('enabled', True) or not repo or not token:
        return
    prefix = str(cfg.get('budgeted_run_name_prefix', 'budgeted|'))
    rules = source_cfg.get('workflow_rules', {})
    tz = ZoneInfo(tz_name)
    for status in cfg.get('statuses', ['queued', 'in_progress']):
        try:
            runs = github_runs(repo, token, status, int(cfg.get('per_page', 100)))
        except Exception:
            continue
        for run in runs:
            run_id = str(run.get('id', ''))
            if exclude_run_id and run_id == str(exclude_run_id):
                continue
            title = str(run.get('display_title') or run.get('name') or '')
            decoded = decode_budgeted_run(title, prefix)
            units_override = None
            if decoded:
                spec_path, units_override = decoded
                spec = load_obj(spec_path)
                job_id = str(spec.get('job_id') or '')
                if job_id and job_id in reserved_job_ids:
                    continue
            else:
                rule = rules.get(str(run.get('path') or ''))
                if not rule or not rule.get('include_queued', True):
                    continue
                units_override = float(rule.get('units', 1.0))
                spec = {'workload': rule.get('workload'), 'metadata': {'forecast': {'jobs': 1.0, 'units': units_override}}}
            workload, jobs, units, cost = estimate_spec(spec, units_override, forecast_cfg)
            when = parse_dt(run.get('run_started_at') or run.get('created_at')) or now
            if workload:
                add_demand(schedule, max(when, now).astimezone(tz).date().isoformat(), workload, jobs, units, cost, f'actions-run:{run_id}')


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--bucket', default=os.environ.get('HF_BUCKET'))
    p.add_argument('--config', default='configs/budget-ledger.yaml')
    p.add_argument('--sources')
    p.add_argument('--output', required=True)
    p.add_argument('--exclude-run-id', default=os.environ.get('GITHUB_RUN_ID'))
    args = p.parse_args()

    cfg = load_config(args.config)
    forecast_cfg = resolved_forecast(cfg)
    source_cfg = load_obj(args.sources or forecast_cfg.get('sources_file', 'configs/forecast-sources.yaml'))
    schedule = deepcopy(load_schedule(forecast_cfg['schedule_file']))
    schedule.setdefault('version', 1)
    schedule.setdefault('dates', {})
    schedule['generated'] = {'at': datetime.now(timezone.utc).isoformat()}

    now = datetime.now(timezone.utc)
    horizon = now + timedelta(days=int(source_cfg.get('horizon_days', 45)))
    reserved = set()
    if args.bucket:
        try:
            states = reservation_state(load_events(args.bucket, cfg['storage']['prefix']))
            reserved = {str(x['reservation'].get('job_id')) for x in states.values() if x.get('reservation') and not x.get('release')}
        except Exception:
            pass

    collect_specs(schedule, source_cfg, forecast_cfg, now, horizon, cfg['timezone'])
    collect_cron(schedule, source_cfg, forecast_cfg, now, horizon, cfg['timezone'])
    collect_runs(schedule, source_cfg, forecast_cfg, now, cfg['timezone'], os.environ.get('GITHUB_REPOSITORY'), os.environ.get('GITHUB_TOKEN'), args.exclude_run_id, reserved)

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(yaml.safe_dump(schedule, allow_unicode=True, sort_keys=True), encoding='utf-8')
    print(json.dumps({'output': str(out), 'dates': len(schedule.get('dates', {}))}, ensure_ascii=False))


if __name__ == '__main__':
    main()
