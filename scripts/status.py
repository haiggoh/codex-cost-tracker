#!/usr/bin/env python3
"""Store and display read-only Codex allowance snapshots."""
import json
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

