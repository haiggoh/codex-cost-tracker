# Three-Pool Status Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a safe terminal dashboard for user-entered native Codex plan and API-credit snapshots beside the existing transcript estimate.

**Architecture:** `scripts/status.py` owns validation, private snapshot persistence, auth-mode inspection, and rendering. It has no network or credential access. `tests/test_status.py` exercises command behavior with temporary directories.

**Tech Stack:** Python 3.9+ standard library and `unittest`.

**Spec:** `docs/superpowers/specs/2026-09-14-three-pool-status-design.md`

## Global Constraints

- Never read, emit, copy, or persist an API key or ChatGPT token.
- State defaults outside the repository and has mode 0600.
- Print unknown rather than zero for unavailable sources.
- No network, dependencies, hooks, or background process.

---

### Task 1: Private snapshot persistence

**Files:**
- Create: `scripts/status.py`
- Create: `tests/test_status.py`

**Interfaces:** Produces `parse_timestamp(value: str) -> str`, `load_state(path: Path) -> tuple[dict, list[str]]`, and `save_state(path: Path, state: dict) -> None`.

- [ ] **Step 1: Write the failing test**

```python
def test_plan_snapshot_round_trip_is_private(self):
    status.save_state(self.state, {'plan': {'remaining_percent': 61.0}})
    loaded, warnings = status.load_state(self.state)
    self.assertEqual(loaded['plan']['remaining_percent'], 61.0)
    self.assertEqual(stat.S_IMODE(self.state.stat().st_mode), 0o600)
    self.assertEqual(warnings, [])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_status.StatusTests.test_plan_snapshot_round_trip_is_private -v`

Expected: FAIL because `scripts/status.py` does not exist.

- [ ] **Step 3: Write minimal implementation**

Write JSON to a sibling temporary file, chmod it 0600, atomically replace the state file, then chmod the result 0600. `load_state` returns an empty dict and warning for invalid JSON or a state file readable by group or other users.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_status.StatusTests.test_plan_snapshot_round_trip_is_private -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/status.py tests/test_status.py
git commit -m "Add private status snapshot storage"
```

### Task 2: Snapshot commands

**Files:**
- Modify: `scripts/status.py`
- Modify: `tests/test_status.py`

**Interfaces:** Consumes Task 1 storage. Produces `main(argv=None) -> int`, with `snapshot-plan` and `snapshot-api-credit` commands.

- [ ] **Step 1: Write failing tests**

```python
def test_snapshot_plan_records_native_cli_provenance(self):
    code = status.main(['--state', str(self.state), 'snapshot-plan',
                        '--remaining-percent', '61', '--reset-at',
                        '2026-10-14T16:00:00+00:00'])
    self.assertEqual(code, 0)
    state, _ = status.load_state(self.state)
    self.assertEqual(state['plan']['source'],
                     'user-confirmed native CLI /status')

def test_snapshot_plan_rejects_invalid_percentage_without_overwrite(self):
    self.state.write_text('{"plan":{"remaining_percent":61}}')
    with self.assertRaises(SystemExit):
        status.main(['--state', str(self.state), 'snapshot-plan',
                     '--remaining-percent', '101', '--reset-at',
                     '2026-10-14T16:00:00+00:00'])
    self.assertIn('61', self.state.read_text())
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_status -v`

Expected: FAIL because the subcommands are absent.

- [ ] **Step 3: Write minimal implementation**

Use `argparse` subparsers. Validate 0–100 percentages, offset ISO-8601 timestamps, and finite non-negative dollar values before calling `save_state`. Store observed time and a literal provenance label.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_status -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/status.py tests/test_status.py
git commit -m "Add plan and API credit snapshot commands"
```

### Task 3: Dashboard and release

**Files:**
- Modify: `scripts/status.py`
- Modify: `tests/test_status.py`
- Modify: `README.md`
- Modify: `skills/codex-cost/SKILL.md`
- Modify: `CHANGELOG.md`
- Modify: `.codex-plugin/plugin.json`

**Interfaces:** Consumes Tasks 1–2 state and only the `auth_mode` field in `~/.codex/auth.json`. Produces `render_status(state, auth_mode, now) -> str`.

- [ ] **Step 1: Write failing test**

```python
def test_dashboard_identifies_chatgpt_routing_and_unknown_incentive(self):
    output = status.render_status(
        {'plan': {'remaining_percent': 61.0,
                  'source': 'user-confirmed native CLI /status'}},
        auth_mode='chatgpt', now='2026-09-14T16:00:00+00:00')
    self.assertIn('Monthly Codex/Work plan: 61%', output)
    self.assertIn('Current routing: ChatGPT plan', output)
    self.assertIn('Daily API incentive: unknown', output)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_status.StatusTests.test_dashboard_identifies_chatgpt_routing_and_unknown_incentive -v`

Expected: FAIL because `render_status` is absent.

- [ ] **Step 3: Write minimal implementation**

Render four independent rows: monthly plan, daily API incentive, paid API credit, and local transcript estimate. Recognize only `chatgpt` and `apikey` auth modes. Document routing, provenance, and the intentionally unavailable live monthly API. Bump all visible versions to 0.2.0.

- [ ] **Step 4: Run validation**

```bash
python3 -m unittest discover -s tests -v
python3 scripts/status.py --help
python3 scripts/report.py --help
python3 /Users/bra0002h/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py .
```

Expected: all tests and validation pass.

- [ ] **Step 5: Commit and publish**

```bash
git add scripts/status.py tests/test_status.py README.md skills/codex-cost/SKILL.md CHANGELOG.md .codex-plugin/plugin.json
git commit -m "Add three-pool terminal status dashboard"
git push origin main
git tag v0.2.0
git push origin v0.2.0
```

