import importlib.util
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch


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

    def test_usage_summary_keeps_incentive_and_paid_tiers_separate(self):
        summary = status.summarize_usage({
            'data': [{'start_time': 1, 'end_time': 2, 'results': [
                {'service_tier': 'data_sharing_incentive', 'model': 'gpt-5.6-terra',
                 'input_tokens': 250, 'output_tokens': 75, 'num_model_requests': 2},
                {'service_tier': 'default', 'model': 'gpt-5.6-terra',
                 'input_tokens': 100, 'output_tokens': 20, 'num_model_requests': 1},
            ]}]
        })
        self.assertEqual(summary['incentive']['input_tokens'], 250)
        self.assertEqual(summary['incentive']['output_tokens'], 75)
        self.assertEqual(summary['paid']['input_tokens'], 100)
        self.assertEqual(summary['paid']['requests'], 1)

    def test_usage_summary_rejects_malformed_payload(self):
        with self.assertRaises(ValueError):
            status.summarize_usage({'data': 'not a list'})

    def test_sync_api_stores_daily_usage_and_costs_without_raw_response(self):
        key = Path(self.temporary.name) / 'admin-key'
        key.write_text('test-admin-key')
        key.chmod(0o600)
        responses = [
            {'data': [{'results': [{'service_tier': 'data_sharing_incentive',
                                    'input_tokens': 9, 'output_tokens': 3,
                                    'num_model_requests': 1}]}]},
            {'data': [{'results': [{'amount': {'value': 1.25, 'currency': 'usd'}}]}]},
        ]
        with patch.object(status, 'fetch_admin_json', side_effect=responses):
            code = status.main(['--state', str(self.state), 'sync-api', '--key-file', str(key),
                                '--date', '2026-09-14'])
        self.assertEqual(code, 0)
        stored, warnings = status.load_state(self.state)
        self.assertEqual(warnings, [])
        self.assertEqual(stored['api_usage']['incentive']['input_tokens'], 9)
        self.assertEqual(stored['api_usage']['cost_usd'], 1.25)
        self.assertNotIn('data', stored['api_usage'])


if __name__ == '__main__':
    unittest.main()
