#!/usr/bin/env python3
"""Store and display read-only Codex allowance snapshots."""
import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import sys
from typing import Dict, List, Optional, Tuple


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


def render_status(state: Dict, auth_mode: str, now: str) -> str:
    """Render pool status with clear source boundaries."""
    route = {'chatgpt': 'ChatGPT plan', 'apikey': 'OpenAI API key'}.get(auth_mode, 'unknown')
    plan = state.get('plan', {})
    credit = state.get('api_credit', {})
    if isinstance(plan, dict) and 'remaining_percent' in plan:
        monthly = f"{plan['remaining_percent']:g}% ({plan.get('source', 'unknown source')})"
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
        'Daily API incentive: unknown (requires an authoritative Usage API import)',
        f'Purchased API credit: {api_credit}',
        'Local transcript estimate: use scripts/report.py separately.',
    ))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description='Store and display private Codex allowance snapshots.',
        epilog='Environment: XDG_STATE_HOME selects the default state directory. No credentials, network calls, hooks, or background jobs are used.')
    parser.add_argument('--state', help='Private JSON state file; default $XDG_STATE_HOME/codex-cost-tracker/status.json')
    commands = parser.add_subparsers(dest='command')
    view = commands.add_parser('status', help='Display all separately sourced pool snapshots')
    view.add_argument('--auth-file', type=Path,
                      default=Path(os.environ.get('CODEX_HOME', '~/.codex')).expanduser() / 'auth.json',
                      help='Codex auth file; only its auth_mode field is read')
    plan = commands.add_parser('snapshot-plan', help='Record a native Codex CLI /status reading')
    plan.add_argument('--remaining-percent', required=True, type=float)
    plan.add_argument('--reset-at', required=True, help='ISO-8601 timestamp with UTC offset')
    plan.add_argument('--observed-at', help='ISO-8601 timestamp with UTC offset; default current UTC')
    credit = commands.add_parser('snapshot-api-credit', help='Record a Billing-page API credit balance')
    credit.add_argument('--usd', required=True, type=float)
    credit.add_argument('--observed-at', help='ISO-8601 timestamp with UTC offset; default current UTC')
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
    observed = parse_timestamp(args.observed_at) if args.observed_at else datetime.now(timezone.utc).isoformat()
    if args.command == 'snapshot-plan':
        if not math.isfinite(args.remaining_percent) or not 0 <= args.remaining_percent <= 100:
            parser.error('--remaining-percent must be a finite number from 0 through 100')
        try:
            reset_at = parse_timestamp(args.reset_at)
        except ValueError as exc:
            parser.error(str(exc))
        state['plan'] = {'remaining_percent': args.remaining_percent, 'reset_at': reset_at,
                         'observed_at': observed, 'source': 'user-confirmed native CLI /status'}
    else:
        if not math.isfinite(args.usd) or args.usd < 0:
            parser.error('--usd must be a finite non-negative number')
        state['api_credit'] = {'usd': args.usd, 'observed_at': observed,
                               'source': 'user-confirmed OpenAI Billing page'}
    save_state(path, state)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
