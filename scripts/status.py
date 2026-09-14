#!/usr/bin/env python3
"""Store and display read-only Codex allowance snapshots."""
import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
from typing import Dict, List, Tuple


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


def state_path(value: str | None) -> Path:
    if value:
        return Path(value).expanduser()
    root = Path(os.environ.get('XDG_STATE_HOME', '~/.local/state')).expanduser()
    return root / 'codex-cost-tracker' / 'status.json'


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description='Store and display private Codex allowance snapshots.',
        epilog='Environment: XDG_STATE_HOME selects the default state directory. No credentials, network calls, hooks, or background jobs are used.')
    parser.add_argument('--state', help='Private JSON state file; default $XDG_STATE_HOME/codex-cost-tracker/status.json')
    commands = parser.add_subparsers(dest='command')
    plan = commands.add_parser('snapshot-plan', help='Record a native Codex CLI /status reading')
    plan.add_argument('--remaining-percent', required=True, type=float)
    plan.add_argument('--reset-at', required=True, help='ISO-8601 timestamp with UTC offset')
    plan.add_argument('--observed-at', help='ISO-8601 timestamp with UTC offset; default current UTC')
    credit = commands.add_parser('snapshot-api-credit', help='Record a Billing-page API credit balance')
    credit.add_argument('--usd', required=True, type=float)
    credit.add_argument('--observed-at', help='ISO-8601 timestamp with UTC offset; default current UTC')
    args = parser.parse_args(argv)
    path = state_path(args.state)
    if args.command is None:
        parser.error('choose snapshot-plan or snapshot-api-credit')
    state, warnings = load_state(path)
    if warnings:
        parser.error('; '.join(warnings))
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
