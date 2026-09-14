import importlib.util
from datetime import date, timedelta
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

    def test_plan_snapshot_allows_native_percentage_without_a_reset_time(self):
        code = status.main(['--state', str(self.state), 'snapshot-plan',
                            '--remaining-percent', '61'])
        self.assertEqual(code, 0)
        state, warnings = status.load_state(self.state)
        self.assertEqual(warnings, [])
        self.assertEqual(state['plan']['remaining_percent'], 61.0)
        self.assertNotIn('reset_at', state['plan'])

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
                {'service_tier': 'incentivized-tier', 'model': 'gpt-5.6-terra',
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

    def test_key_name_lookup_selects_one_exact_admin_api_key(self):
        key_id = status.select_api_key_id({'data': [
            {'id': 'key_elsewhere', 'name': 'Other key'},
            {'id': 'key_codex', 'name': 'Codex-api'},
        ]}, 'Codex-api')
        self.assertEqual(key_id, 'key_codex')

    def test_key_name_lookup_rejects_ambiguous_names(self):
        with self.assertRaises(ValueError):
            status.select_api_key_id({'data': [
                {'id': 'key_one', 'name': 'Codex-api'},
                {'id': 'key_two', 'name': 'Codex-api'},
            ]}, 'Codex-api')

    def test_dashboard_labels_a_usage_filter_by_api_key_name(self):
        output = status.render_status({'api_usage': {
            'day': '2026-09-14', 'api_key_name': 'Codex-api',
            'incentive': {'input_tokens': 1, 'output_tokens': 2, 'requests': 3},
            'paid': {'input_tokens': 4, 'output_tokens': 5, 'requests': 6},
            'cost_usd': 1.25,
        }}, auth_mode='apikey', now='2026-09-14T16:00:00+00:00')
        self.assertIn('API key filter: Codex-api', output)

    def test_dashboard_shows_incentive_cap_percentage(self):
        output = status.render_status({'incentive_cap': {'daily_tokens': 20}, 'api_usage': {
            'day': '2026-09-14',
            'incentive': {'input_tokens': 10, 'output_tokens': 5, 'requests': 1},
            'paid': {'input_tokens': 0, 'output_tokens': 0, 'requests': 0},
        }}, auth_mode='apikey', now='2026-09-14T16:00:00+00:00')
        self.assertIn('15 / 20 tokens = 75.0% used', output)

    def test_dashboard_shows_credit_consumption_since_purchase_baseline(self):
        output = status.render_status({'api_credit': {'usd': 50, 'costs_since': '2026-09-01'},
                                       'api_usage': {'costs_since_usd': 12.5,
                                                     'costs_since': '2026-09-01'}},
                                      auth_mode='apikey', now='2026-09-14T16:00:00+00:00')
        self.assertIn('$12.50 / $50.00 = 25.0% used', output)
        self.assertIn('$37.50 estimated remaining', output)

    def test_credit_snapshot_records_a_costs_baseline_date(self):
        code = status.main(['--state', str(self.state), 'snapshot-api-credit', '--usd', '50',
                            '--costs-since', '2026-09-01'])
        self.assertEqual(code, 0)
        stored, warnings = status.load_state(self.state)
        self.assertEqual(warnings, [])
        self.assertEqual(stored['api_credit']['costs_since'], '2026-09-01')

    def test_incentive_cap_snapshot_records_available_daily_tokens(self):
        code = status.main(['--state', str(self.state), 'snapshot-incentive-cap', '--daily-tokens', '100'])
        self.assertEqual(code, 0)
        stored, warnings = status.load_state(self.state)
        self.assertEqual(warnings, [])
        self.assertEqual(stored['incentive_cap']['daily_tokens'], 100)

    def test_cost_history_requests_multiple_180_day_windows(self):
        document = {'data': [{'results': [{'amount': {'value': 2.0, 'currency': 'usd'}}]}]}
        with patch.object(status, 'fetch_admin_json', return_value=document) as fetch:
            total = status.fetch_costs_since(Path('unused'), date(2026, 1, 1),
                                             date(2026, 1, 1) + timedelta(days=180))
        self.assertEqual(total, 4.0)
        self.assertEqual(fetch.call_count, 2)

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
