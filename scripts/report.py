#!/usr/bin/env python3
"""Read-only Codex desktop/CLI token-cost estimates, independent of Claude/Joyia."""
import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import sys
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

VERSION = '0.1.0'
PRICING_DATE = '2026-09-14'
PRICING_URL = 'https://developers.openai.com/api/docs/models/gpt-6-astra'
# Ordinary input, cached input, cache writes, output: USD / million tokens.
RATES = {'gpt-6-astra': (10, 1, 12.5, 50)}
FIELDS = ('input_tokens', 'cached_input_tokens', 'cache_write_input_tokens',
          'output_tokens', 'reasoning_output_tokens', 'total_tokens')


def normalized(value):
    if not isinstance(value, dict):
        raise ValueError('missing usage object')
    if any(k not in value for k in FIELDS[:4]):
        raise ValueError('missing input/output/cache breakdown')
    result = {k: value.get(k, 0) for k in FIELDS}
    if any(type(v) is not int or v < 0 for v in result.values()):
        raise ValueError('negative or noninteger usage')
    if result['cached_input_tokens'] + result['cache_write_input_tokens'] > result['input_tokens']:
        raise ValueError('cache categories exceed input tokens')
    if result['reasoning_output_tokens'] > result['output_tokens']:
        raise ValueError('reasoning exceeds output tokens')
    if result['total_tokens'] != result['input_tokens'] + result['output_tokens']:
        raise ValueError('total-only import or inconsistent total')
    return result


def price(usage, model):
    u = normalized(usage)
    if model not in RATES:
        raise ValueError('unpriced model: ' + str(model))
    i, c, w, o = RATES[model]
    if u['input_tokens'] > 272000:
        i, c, w, o = i * 2, c * 2, w * 2, o * 1.5
    ordinary = u['input_tokens'] - u['cached_input_tokens'] - u['cache_write_input_tokens']
    return (ordinary * i + u['cached_input_tokens'] * c +
            u['cache_write_input_tokens'] * w + u['output_tokens'] * o) / 1_000_000


def build_report(home, date=None, tz='UTC', session=None, tier='auto', budget=None,
                 account_spend=None, account_window=None):
    zone = ZoneInfo(tz)
    result = dict(version=VERSION, generated_at=datetime.now(timezone.utc).isoformat(),
                  period=date or 'all time', timezone=tz, scope='local Codex transcripts only',
                  cost_kind='estimated model tokens; excludes separately billed tools and taxes',
                  pricing_verified=PRICING_DATE, pricing_source=PRICING_URL,
                  tier=tier, standard_usd=0.0, fast_usd=0.0, estimated_usd=0.0,
                  actual_charged_usd=account_spend, actual_charged_window=account_window,
                  actual_charged_source=('user-reported OpenAI Usage dashboard' if account_spend is not None else None),
                  account_credit_balance_usd=None,
                  priced_responses=0, unpriced_responses=0, sessions=[], warnings=[], budget=None)
    seen_sessions = set()
    paths = sorted({p.resolve() for folder in ('sessions', 'archived_sessions')
                    for p in (Path(home) / folder).rglob('*.jsonl')})
    for path in paths:
        row = dict(session_id=None, originator=None, models=[], standard_usd=0.0,
                   fast_usd=0.0, estimated_usd=0.0, priced_responses=0,
                   unpriced_responses=0, last_usage_at=None, warnings=[])
        prev = None
        model = None
        captured_tier = None
        provider = None
        born = None
        forked = False
        selected = session is None
        try:
            stream = path.open()
        except OSError as exc:
            result['warnings'].append(f'{path.name}: {exc.strerror}')
            continue
        with stream:
            for number, line in enumerate(stream, 1):
                try:
                    record = json.loads(line)
                    payload = record.get('payload', {})
                    if not isinstance(payload, dict):
                        continue
                except (ValueError, AttributeError):
                    row['warnings'].append(f'Unreadable record at line {number}; skipped')
                    continue
                if record.get('type') == 'session_meta':
                    sid = payload.get('id')
                    if sid in seen_sessions:
                        break
                    row['session_id'] = sid
                    row['originator'] = payload.get('originator', 'unknown')
                    provider = payload.get('model_provider')
                    forked = bool(payload.get('forked_from_id'))
                    born = payload.get('timestamp', record.get('timestamp'))
                    selected = session is None or sid == session
                    if not selected:
                        break
                    if sid:
                        seen_sessions.add(sid)
                if record.get('type') == 'turn_context':
                    model = payload.get('model')
                    captured_tier = payload.get('service_tier')
                if payload.get('type') != 'token_count' or not payload.get('info'):
                    continue
                info = payload['info']
                total = info.get('total_token_usage')
                last = info.get('last_token_usage')
                stamp = record.get('timestamp')
                try:
                    instant = datetime.fromisoformat(stamp.replace('Z', '+00:00'))
                    in_period = date is None or instant.astimezone(zone).date().isoformat() == date
                except (TypeError, ValueError, AttributeError):
                    row['warnings'].append('Usage record has invalid timestamp; skipped')
                    continue
                if forked and born and stamp < born:
                    prev = total
                    continue
                if total == prev:
                    continue
                previous = prev
                prev = total
                if not in_period:
                    continue
                row['last_usage_at'] = stamp
                try:
                    t = normalized(total)
                    u = normalized(last)
                    if not t['total_tokens'] and not u['total_tokens']:
                        continue
                    if previous is not None:
                        p = normalized(previous)
                        delta = {k: t[k] - p[k] for k in FIELDS}
                        if delta != u:
                            row['warnings'].append('Counter gap/reset: only the last known response is priced; coverage incomplete')
                    elif t != u and not forked:
                        row['warnings'].append('Earlier cumulative usage has no request breakdown; only the last response is priced')
                    if provider != 'openai':
                        raise ValueError('provider is not confirmed OpenAI: ' + str(provider))
                    value = price(u, model)
                    row['standard_usd'] += value
                    row['fast_usd'] += value * 2
                    effective_tier = tier if tier != 'auto' else captured_tier
                    if effective_tier in ('default', 'standard'):
                        if row['estimated_usd'] is not None:
                            row['estimated_usd'] += value
                    elif effective_tier in ('priority', 'fast'):
                        if row['estimated_usd'] is not None:
                            row['estimated_usd'] += value * 2
                    else:
                        row['estimated_usd'] = None
                    row['priced_responses'] += 1
                    if model not in row['models']:
                        row['models'].append(model)
                except (ValueError, TypeError) as exc:
                    row['unpriced_responses'] += 1
                    row['warnings'].append(str(exc))
        if not selected or not (row['priced_responses'] or row['unpriced_responses'] or row['warnings']):
            continue
        row['warnings'] = sorted(set(row['warnings']))
        result['sessions'].append(row)
        for key in ('standard_usd', 'fast_usd', 'priced_responses', 'unpriced_responses'):
            result[key] += row[key]
        if row['estimated_usd'] is None:
            result['estimated_usd'] = None
        elif result['estimated_usd'] is not None:
            result['estimated_usd'] += row['estimated_usd']
        result['warnings'].extend(f"{row['session_id']}: {w}" for w in row['warnings'])
    if account_spend is not None and (not math.isfinite(account_spend) or account_spend < 0):
        raise ValueError('account spend must be a finite non-negative number')
    if account_spend is not None and not account_window:
        raise ValueError('account window is required with account spend')
    if session and session not in seen_sessions:
        result['warnings'].append('Requested session not found')
    if not paths:
        result['warnings'].append('No local transcript files found')
    if budget is not None:
        result['budget'] = dict(usd=budget, source='user-supplied reporting cap; not account credit balance',
                                remaining_usd=None if result['estimated_usd'] is None or result['warnings'] else budget - result['estimated_usd'])
    return result


def main():
    parser = argparse.ArgumentParser(description='Estimate Codex desktop and CLI model-token costs from local transcripts.',
        epilog='Environment: CODEX_HOME selects the data directory (default ~/.codex). No keys, network, hooks, or background jobs are used. Auto tier shows Standard/Fast scenarios when the actual tier is missing.')
    parser.add_argument('--version', action='version', version=VERSION)
    parser.add_argument('--home', type=Path, default=Path(os.environ.get('CODEX_HOME', '~/.codex')).expanduser(), help='Codex data directory')
    periods = parser.add_mutually_exclusive_group()
    periods.add_argument('--date', help='Calendar date YYYY-MM-DD; default today in --timezone')
    periods.add_argument('--all-time', action='store_true', help='All recorded dates')
    parser.add_argument('--timezone', default='UTC', help='IANA timezone for day boundaries, default UTC')
    parser.add_argument('--session', help='Exact task/session ID; default all local sessions')
    parser.add_argument('--tier', choices=('auto', 'standard', 'fast'), default='auto', help='Use recorded tier or explicitly select a pricing assumption')
    parser.add_argument('--budget-usd', type=float, help='Optional user-supplied cap for the selected reporting period; not an account balance')
    parser.add_argument('--account-spend-usd', type=float, help='Spend shown by the OpenAI Usage dashboard; requires --account-window')
    parser.add_argument('--account-window', help='Exact dashboard window for --account-spend-usd, e.g. "last 7 days"')
    parser.add_argument('--json', action='store_true', help='Machine-readable report')
    args = parser.parse_args()
    try:
        zone = ZoneInfo(args.timezone)
        day = None if args.all_time else args.date or datetime.now(zone).date().isoformat()
        if day:
            datetime.strptime(day, '%Y-%m-%d')
        if args.budget_usd is not None and (not math.isfinite(args.budget_usd) or args.budget_usd <= 0):
            parser.error('--budget-usd must be a positive finite number')
        result = build_report(args.home.expanduser(), day, args.timezone, args.session, args.tier, args.budget_usd,
                              args.account_spend_usd, args.account_window)
    except (ValueError, ZoneInfoNotFoundError) as exc:
        parser.error(str(exc))
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"Codex cost tracker {VERSION} — {result['period']} ({args.timezone})")
        print('Estimated model-token cost; excludes tool fees, taxes, and usage outside these local transcripts.')
        print(f"{'Task':36}  {'Standard USD':>12}  {'Fast USD':>10}  {'Priced':>6}  {'Unpriced':>8}")
        for row in result['sessions']:
            print(f"{str(row['session_id']):36}  {row['standard_usd']:12.4f}  {row['fast_usd']:10.4f}  {row['priced_responses']:6}  {row['unpriced_responses']:8}")
        print(f"TOTAL: Standard ${result['standard_usd']:.4f}; Fast ${result['fast_usd']:.4f}")
        if result['estimated_usd'] is None:
            print('Actual processing tier missing: these are scenarios, not a confirmed billed amount.')
        else:
            print(f"Selected/recorded tier estimate: ${result['estimated_usd']:.4f} ({args.tier})")
        print('Local token records do not provide actual account charges or remaining credit.')
        if result['actual_charged_usd'] is not None:
            print(f"Account dashboard spend: ${result['actual_charged_usd']:.2f} ({result['actual_charged_window']}; {result['actual_charged_source']}).")
        if result['budget']:
            print('Reporting cap:', json.dumps(result['budget']))
        if result['warnings']:
            print(f"Coverage incomplete: {result['unpriced_responses']} unpriced record(s).")
            for warning in result['warnings']:
                print('  - ' + warning)
        print('Pricing source: ' + PRICING_URL + ' (verified ' + PRICING_DATE + ')')
    return 0


if __name__ == '__main__':
    sys.exit(main())
