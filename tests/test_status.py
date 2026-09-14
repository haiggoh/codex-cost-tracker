import importlib.util
from pathlib import Path
import stat
import tempfile
import unittest


SPEC = importlib.util.spec_from_file_location(
    'status', Path(__file__).parents[1] / 'scripts' / 'status.py')
status = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(status)


class StatusTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.state = Path(self.temporary.name) / 'status.json'

    def test_plan_snapshot_round_trip_is_private(self):
        status.save_state(self.state, {'plan': {'remaining_percent': 61.0}})
        loaded, warnings = status.load_state(self.state)
        self.assertEqual(loaded['plan']['remaining_percent'], 61.0)
        self.assertEqual(stat.S_IMODE(self.state.stat().st_mode), 0o600)
        self.assertEqual(warnings, [])

    def test_snapshot_plan_records_native_cli_provenance(self):
        code = status.main(['--state', str(self.state), 'snapshot-plan',
                            '--remaining-percent', '61', '--reset-at',
                            '2026-10-14T16:00:00+00:00'])
        self.assertEqual(code, 0)
        state, warnings = status.load_state(self.state)
        self.assertEqual(warnings, [])
        self.assertEqual(state['plan']['remaining_percent'], 61.0)
        self.assertEqual(state['plan']['source'], 'user-confirmed native CLI /status')

    def test_snapshot_plan_rejects_invalid_percentage_without_overwrite(self):
        status.save_state(self.state, {'plan': {'remaining_percent': 61}})
        with self.assertRaises(SystemExit):
            status.main(['--state', str(self.state), 'snapshot-plan',
                         '--remaining-percent', '101', '--reset-at',
                         '2026-10-14T16:00:00+00:00'])
        state, warnings = status.load_state(self.state)
        self.assertEqual(warnings, [])
        self.assertEqual(state['plan']['remaining_percent'], 61)

    def test_dashboard_identifies_chatgpt_routing_and_unknown_incentive(self):
        output = status.render_status(
            {'plan': {'remaining_percent': 61.0,
                      'source': 'user-confirmed native CLI /status'}},
            auth_mode='chatgpt', now='2026-09-14T16:00:00+00:00')
        self.assertIn('Monthly Codex/Work plan: 61%', output)
        self.assertIn('Current routing: ChatGPT plan', output)
        self.assertIn('Daily API incentive: unknown', output)

    def test_dashboard_includes_the_plan_reset_timestamp(self):
        output = status.render_status(
            {'plan': {'remaining_percent': 61.0,
                      'reset_at': '2026-10-14T16:00:00+00:00',
                      'source': 'user-confirmed native CLI /status'}},
            auth_mode='chatgpt', now='2026-09-14T16:00:00+00:00')
        self.assertIn('resets 2026-10-14T16:00:00+00:00', output)

    def test_unknown_auth_mode_never_exposes_auth_file_fields(self):
        auth = Path(self.temporary.name) / 'auth.json'
        auth.write_text('{"auth_mode":"unexpected","tokens":{"access_token":"secret"}}')
        self.assertEqual(status.read_auth_mode(auth), 'unknown')

    def test_status_command_renders_missing_snapshots_as_unknown(self):
        code = status.main(['--state', str(self.state), 'status', '--auth-file',
                            str(Path(self.temporary.name) / 'missing-auth.json')])
        self.assertEqual(code, 0)


if __name__ == '__main__':
    unittest.main()
