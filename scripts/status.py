#!/usr/bin/env python3
"""Store and display read-only Codex allowance snapshots."""
import argparse
from datetime import date, datetime, timedelta, timezone
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlencode


def load_state(path: Path) -> Tuple[Dict, List[str]]:
    """Load a private snapshot, returning warnings instead of raising for bad input."""
    if not path.exists():
        return {}, []
    if path.stat().st_mode & 0o077:
        return {}, [f'{path}: state file permissions are not private']
    try:
        value = json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        return {}, [f'{path}: unreadable state ({exc})']
    if not isinstance(value, dict):
        return {}, [f'{path}: state must be a JSON object']
    return value, []


def save_state(path: Path, state: Dict) -> None:
    """Atomically save a private JSON snapshot."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    try:
        temporary.write_text(json.dumps(state, indent=2, sort_keys=True) + '\n')
        os.chmod(temporary, 0o600)
        temporary.replace(path)
        os.chmod(path, 0o600)
    finally:
        if temporary.exists():
            temporary.unlink()


def parse_timestamp(value: str) -> str:
    """Normalize an ISO-8601 timestamp that includes its UTC offset."""
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('timestamp must include a UTC offset')
    return parsed.isoformat()


def state_path(value: Optional[str]) -> Path:
    if value:
        return Path(value).expanduser()
    root = Path(os.environ.get('XDG_STATE_HOME', '~/.local/state')).expanduser()
    return root / 'codex-cost-tracker' / 'status.json'


def read_auth_mode(path: Path) -> str:
    """Read only the non-secret authentication mode from Codex state."""
    try:
        value = json.loads(path.read_text())
    except (OSError, ValueError):
        return 'unknown'
    mode = value.get('auth_mode') if isinstance(value, dict) else None
    return mode if mode in ('chatgpt', 'apikey') else 'unknown'


def summarize_usage(document: Dict) -> Dict:
    """Summarize one Usage API response without retaining individual records."""
    buckets = document.get('data')
    if not isinstance(buckets, list):
        raise ValueError('Usage API response has no data list')
    summary = {
        'incentive': {'input_tokens': 0, 'output_tokens': 0, 'requests': 0},
        'paid': {'input_tokens': 0, 'output_tokens': 0, 'requests': 0},
    }
    for bucket in buckets:
        if not isinstance(bucket, dict) or not isinstance(bucket.get('results'), list):
            raise ValueError('Usage API response has malformed buckets')
        for row in bucket['results']:
            if not isinstance(row, dict):
                raise ValueError('Usage API response has malformed results')
            tier = str(row.get('service_tier') or '').lower()
            category = 'incentive' if tier in ('incentivized-tier', 'data_sharing_incentive') else 'paid'
            for field, output in (('input_tokens', 'input_tokens'),
                                  ('output_tokens', 'output_tokens'),
                                  ('num_model_requests', 'requests')):
                value = row.get(field, 0)
                if not isinstance(value, int) or value < 0:
                    raise ValueError(f'Usage API response has invalid {field}')
                summary[category][output] += value
    return summary


def select_api_key_id(document: Dict, name: str) -> str:
    """Select exactly one API key ID by its user-visible name."""
    keys = document.get('data')
    if not isinstance(keys, list):
        raise ValueError('Admin API key response has no data list')
    matches = [key.get('id') for key in keys if isinstance(key, dict) and key.get('name') == name
               and isinstance(key.get('id'), str)]
    if len(matches) != 1:
        raise ValueError(f'expected exactly one Admin API key named {name!r}; found {len(matches)}')
    return matches[0]


def summarize_costs(document: Dict) -> float:
    """Return total USD reported by one Costs API response."""
    buckets = document.get('data')
    if not isinstance(buckets, list):
        raise ValueError('Costs API response has no data list')
    total = 0.0
    for bucket in buckets:
        if not isinstance(bucket, dict) or not isinstance(bucket.get('results'), list):
            raise ValueError('Costs API response has malformed buckets')
        for row in bucket['results']:
            amount = row.get('amount') if isinstance(row, dict) else None
            if not isinstance(amount, dict) or amount.get('currency') != 'usd':
                raise ValueError('Costs API response has a non-USD or malformed amount')
            value = amount.get('value')
            if not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                raise ValueError('Costs API response has an invalid amount')
            total += value
    return total


def fetch_costs_since(key_file: Path, since: date, through: date) -> float:
    """Sum daily Costs API buckets from a purchase baseline through a UTC day."""
    total = 0.0
    cursor = since
    while cursor <= through:
        stop = min(cursor + timedelta(days=180), through + timedelta(days=1))
        start_time = int(datetime.combine(cursor, datetime.min.time(), timezone.utc).timestamp())
        end_time = int(datetime.combine(stop, datetime.min.time(), timezone.utc).timestamp())
        document = fetch_admin_json('https://api.openai.com/v1/organization/costs', [
            ('start_time', str(start_time)), ('end_time', str(end_time)),
            ('bucket_width', '1d'), ('limit', '180')], key_file)
        total += summarize_costs(document)
        cursor = stop
    return total


def fetch_admin_json(endpoint: str, query: List[Tuple[str, str]], key_file: Path) -> Dict:
    """Make a read-only Admin API request without exposing its credential in argv."""
    if not key_file.is_file() or not key_file.read_text(encoding='utf-8').strip():
        raise ValueError(f'key file is missing or empty: {key_file}')
    if key_file.stat().st_mode & 0o077:
        raise ValueError(f'key file permissions are not private: {key_file}')
    key = key_file.read_text(encoding='utf-8').strip()
    url = endpoint + '?' + urlencode(query)
    with tempfile.TemporaryDirectory(prefix='codex-cost-tracker-') as directory:
        root = Path(directory)
        config = root / 'curl.conf'
        output = root / 'response.json'
        config.write_text('silent\nshow-error\nheader = "Authorization: Bearer ' + key + '"\n')
        os.chmod(config, 0o600)
        result = subprocess.run(['curl', '--fail', '--config', str(config), '--output', str(output),
                                 '--write-out', '%{http_code}', url],
                                capture_output=True, text=True, check=False)
        if result.returncode:
            status = result.stdout.strip()
            detail = f'HTTP {status}' if status.isdigit() else 'an access or network error'
            raise ValueError(f'OpenAI Admin API request failed: {detail}. See README for Admin Key setup.')
        try:
            return json.loads(output.read_text(encoding='utf-8'))
        except (OSError, ValueError) as exc:
            raise ValueError(f'OpenAI Admin API returned invalid JSON: {exc}') from exc


def render_status(state: Dict, auth_mode: str, now: str) -> str:
    """Render pool status with clear source boundaries."""
    route = {'chatgpt': 'ChatGPT plan', 'apikey': 'OpenAI API key'}.get(auth_mode, 'unknown')
    plan = state.get('plan', {})
    credit = state.get('api_credit', {})
    if isinstance(plan, dict) and 'remaining_percent' in plan:
        reset = plan.get('reset_at')
        reset_text = f'; resets {reset}' if reset else ''
        monthly = f"{plan['remaining_percent']:g}% ({plan.get('source', 'unknown source')}{reset_text})"
    else:
        monthly = 'unknown'
    if isinstance(credit, dict) and 'usd' in credit:
        api_credit = f"${credit['usd']:.2f} ({credit.get('source', 'unknown source')})"
    else:
        api_credit = 'unknown'
    return '\n'.join((
        f'Codex Cost Tracker status — observed {now}',
        f'Current routing: {route}',
        f'Monthly Codex/Work plan: {monthly}',
        daily_api_line(state),
        paid_api_line(state),
        f'Purchased API credit: {api_credit}',
        credit_consumption_line(state),
        'Local transcript estimate: use scripts/report.py separately.',
    ))


def daily_api_line(state: Dict) -> str:
    api = state.get('api_usage')
    if not isinstance(api, dict) or not isinstance(api.get('incentive'), dict):
        return 'Daily API incentive: unknown (run sync-api with an OpenAI Admin Key)'
    tier = api['incentive']
    filter_label = api.get('api_key_name')
    filter_text = f'; API key filter: {filter_label}' if isinstance(filter_label, str) else ''
    line = ('Daily API incentive: {input_tokens} input, {output_tokens} output, {requests} requests '
            '(authoritative API Usage; {day} UTC{filter_text})').format(
                day=api.get('day', 'unknown'), filter_text=filter_text, **tier)
    cap = state.get('incentive_cap')
    if isinstance(cap, dict) and isinstance(cap.get('daily_tokens'), int) and cap['daily_tokens'] > 0:
        used = tier['input_tokens'] + tier['output_tokens']
        line += f"; {used} / {cap['daily_tokens']} tokens = {used / cap['daily_tokens'] * 100:.1f}% used"
    else:
        line += '; cap unknown (record snapshot-incentive-cap)'
    return line


def paid_api_line(state: Dict) -> str:
    api = state.get('api_usage')
    if not isinstance(api, dict) or not isinstance(api.get('paid'), dict):
        return 'Paid API usage today: unknown'
    tier = api['paid']
    line = ('Paid API usage today: {input_tokens} input, {output_tokens} output, {requests} requests '
            '(authoritative API Usage; {day} UTC; costs may lag)').format(day=api.get('day', 'unknown'), **tier)
    if isinstance(api.get('cost_usd'), (int, float)):
        line += f"; organization daily API Costs: ${api['cost_usd']:.2f}"
    return line


def credit_consumption_line(state: Dict) -> str:
    credit = state.get('api_credit')
    api = state.get('api_usage')
    if not isinstance(credit, dict) or not isinstance(credit.get('usd'), (int, float)):
        return 'Prepaid credit consumption: unknown (record snapshot-api-credit)'
    if not isinstance(api, dict) or not isinstance(api.get('costs_since_usd'), (int, float)):
        return 'Prepaid credit consumption: unknown (record a purchase baseline and run sync-api)'
    spent = api['costs_since_usd']
    purchased = credit['usd']
    remaining = purchased - spent
    return (f'Prepaid credit consumption: ${spent:.2f} / ${purchased:.2f} = '
            f'{spent / purchased * 100:.1f}% used; ${remaining:.2f} estimated remaining '
            f"(Costs since {api.get('costs_since', 'unknown')} UTC)")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description='Store and display private Codex allowance snapshots.',
        epilog='Environment: XDG_STATE_HOME selects the default state directory. sync-api reads a user-supplied Admin Key file and makes read-only Usage/Costs requests; all other commands use no credentials or network. No hooks or background jobs are used.')
    parser.add_argument('--state', help='Private JSON state file; default $XDG_STATE_HOME/codex-cost-tracker/status.json')
    commands = parser.add_subparsers(dest='command')
    view = commands.add_parser('status', help='Display all separately sourced pool snapshots')
    view.add_argument('--auth-file', type=Path,
                      default=Path(os.environ.get('CODEX_HOME', '~/.codex')).expanduser() / 'auth.json',
                      help='Codex auth file; only its auth_mode field is read')
    plan = commands.add_parser('snapshot-plan', help='Record a native Codex CLI /status reading')
    plan.add_argument('--remaining-percent', required=True, type=float)
    plan.add_argument('--reset-at', help='Optional ISO-8601 reset timestamp with UTC offset')
    plan.add_argument('--observed-at', help='ISO-8601 timestamp with UTC offset; default current UTC')
    credit = commands.add_parser('snapshot-api-credit', help='Record a Billing-page API credit balance')
    credit.add_argument('--usd', required=True, type=float)
    credit.add_argument('--costs-since', help='UTC purchase-baseline day as YYYY-MM-DD')
    credit.add_argument('--observed-at', help='ISO-8601 timestamp with UTC offset; default current UTC')
    incentive = commands.add_parser('snapshot-incentive-cap',
                                    help='Record the available daily data-sharing incentive cap')
    incentive.add_argument('--daily-tokens', required=True, type=int)
    incentive.add_argument('--observed-at', help='ISO-8601 timestamp with UTC offset; default current UTC')
    sync = commands.add_parser('sync-api', help='Read daily Usage and Costs with an OpenAI Admin Key')
    sync.add_argument('--key-file', required=True, type=Path,
                      help='Private file containing one OpenAI Admin Key')
    sync.add_argument('--date', help='UTC day to read as YYYY-MM-DD; default today')
    selector = sync.add_mutually_exclusive_group()
    selector.add_argument('--api-key-id', help='Optional API key ID to filter Usage only')
    selector.add_argument('--api-key-name', help='Optional exact API key name to filter Usage only')
    arguments = list(sys.argv[1:] if argv is None else argv)
    if not arguments:
        arguments = ['status']
    args = parser.parse_args(arguments)
    path = state_path(args.state)
    state, warnings = load_state(path)
    if warnings:
        parser.error('; '.join(warnings))
    if args.command == 'status':
        print(render_status(state, read_auth_mode(args.auth_file), datetime.now(timezone.utc).isoformat()))
        return 0
    if args.command == 'sync-api':
        try:
            selected_day = date.fromisoformat(args.date) if args.date else datetime.now(timezone.utc).date()
        except ValueError:
            parser.error('--date must be YYYY-MM-DD')
        start = int(datetime.combine(selected_day, datetime.min.time(), timezone.utc).timestamp())
        end = int((datetime.combine(selected_day, datetime.min.time(), timezone.utc) + timedelta(days=1)).timestamp())
        query = [('start_time', str(start)), ('end_time', str(end)), ('bucket_width', '1d'), ('limit', '1')]
        try:
            key_file = args.key_file.expanduser()
            api_key_id = args.api_key_id
            if args.api_key_name:
                keys_document = fetch_admin_json('https://api.openai.com/v1/organization/admin_api_keys',
                                                 [('limit', '100')], key_file)
                api_key_id = select_api_key_id(keys_document, args.api_key_name)
            usage_query = list(query)
            if api_key_id:
                usage_query.append(('api_key_ids', api_key_id))
            usage_document = fetch_admin_json('https://api.openai.com/v1/organization/usage/completions',
                                              usage_query + [('group_by', 'service_tier'), ('group_by', 'model')],
                                              key_file)
            costs_document = fetch_admin_json('https://api.openai.com/v1/organization/costs', query,
                                              key_file)
            usage = summarize_usage(usage_document)
            costs = summarize_costs(costs_document)
            credit = state.get('api_credit')
            costs_since = None
            cumulative_costs = None
            if isinstance(credit, dict) and isinstance(credit.get('costs_since'), str):
                costs_since = date.fromisoformat(credit['costs_since'])
                cumulative_costs = fetch_costs_since(key_file, costs_since, selected_day)
        except ValueError as exc:
            parser.error(str(exc))
        state['api_usage'] = dict(day=selected_day.isoformat(), observed_at=datetime.now(timezone.utc).isoformat(),
                                  source='OpenAI organization Usage and Costs APIs', cost_usd=costs,
                                  api_key_name=args.api_key_name, **usage)
        if costs_since:
            state['api_usage']['costs_since'] = costs_since.isoformat()
            state['api_usage']['costs_since_usd'] = cumulative_costs
        save_state(path, state)
        return 0
    observed = parse_timestamp(args.observed_at) if args.observed_at else datetime.now(timezone.utc).isoformat()
    if args.command == 'snapshot-plan':
        if not math.isfinite(args.remaining_percent) or not 0 <= args.remaining_percent <= 100:
            parser.error('--remaining-percent must be a finite number from 0 through 100')
        reset_at = None
        if args.reset_at:
            try:
                reset_at = parse_timestamp(args.reset_at)
            except ValueError as exc:
                parser.error(str(exc))
        state['plan'] = {'remaining_percent': args.remaining_percent,
                         'observed_at': observed, 'source': 'user-confirmed native CLI /status'}
        if reset_at:
            state['plan']['reset_at'] = reset_at
    elif args.command == 'snapshot-incentive-cap':
        if args.daily_tokens <= 0:
            parser.error('--daily-tokens must be a positive integer')
        state['incentive_cap'] = {'daily_tokens': args.daily_tokens, 'observed_at': observed,
                                  'source': 'user-confirmed available daily incentive cap'}
    elif args.command == 'snapshot-api-credit':
        if not math.isfinite(args.usd) or args.usd < 0:
            parser.error('--usd must be a finite non-negative number')
        state['api_credit'] = {'usd': args.usd, 'observed_at': observed,
                               'source': 'user-confirmed OpenAI Billing page'}
        if args.costs_since:
            try:
                state['api_credit']['costs_since'] = date.fromisoformat(args.costs_since).isoformat()
            except ValueError:
                parser.error('--costs-since must be YYYY-MM-DD')
    save_state(path, state)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
