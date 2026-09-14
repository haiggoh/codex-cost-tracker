import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location('report', Path(__file__).parents[1] / 'scripts' / 'report.py')
report = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(report)


def usage(i, c=0, w=0, o=0, r=0):
    return dict(input_tokens=i, cached_input_tokens=c, cache_write_input_tokens=w,
                output_tokens=o, reasoning_output_tokens=r, total_tokens=i + o)


def event(total, last=None, ts='2026-09-14T12:00:00Z'):
    return dict(type='event_msg', timestamp=ts, payload=dict(type='token_count',
                info=dict(total_token_usage=total, last_token_usage=last or total)))


class ReportTests(unittest.TestCase):
    def scan(self, events, **kwargs):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'sessions').mkdir()
            records = [dict(type='session_meta', timestamp='2026-09-13T00:00:00Z',
                            payload=dict(id='test', model_provider='openai', originator='codex_work_desktop')),
                       dict(type='turn_context', payload=dict(model='gpt-6-astra'))] + events
            (root / 'sessions' / 'test.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in records))
            return report.build_report(root, date='2026-09-14', **kwargs)

    def test_cache_categories_are_not_double_charged_and_reasoning_is_not_added(self):
        self.assertAlmostEqual(report.price(usage(100000, 60000, 30000, 1000, 500), 'gpt-6-astra'), .585)

    def test_long_context_is_per_request_not_session_sum(self):
        self.assertAlmostEqual(report.price(usage(272001, o=1000), 'gpt-6-astra'), 5.51502)
        self.assertAlmostEqual(report.price(usage(272000, o=1000), 'gpt-6-astra'), 2.77)

    def test_repeated_snapshots_are_not_charged_twice(self):
        x = event(usage(100000))
        result = self.scan([x, x])
        self.assertAlmostEqual(result['standard_usd'], 1.0)
        self.assertEqual(result['priced_responses'], 1)

    def test_previous_day_baseline_is_excluded(self):
        result = self.scan([event(usage(100000), ts='2026-09-13T23:00:00Z'),
                            event(usage(200000), usage(100000))])
        self.assertAlmostEqual(result['standard_usd'], 1.0)

    def test_counter_reset_uses_last_request_and_flags_missing_coverage(self):
        result = self.scan([event(usage(100000)), event(usage(50000))])
        self.assertAlmostEqual(result['standard_usd'], 1.5)
        self.assertTrue(result['warnings'])

    def test_missing_model_and_total_only_imports_are_unpriced(self):
        result = self.scan([dict(type='turn_context', payload=dict(model='unknown-model')),
                            event(usage(100000))])
        self.assertEqual(result['unpriced_responses'], 1)
        self.assertEqual(result['standard_usd'], 0)
        u = usage(0); u['total_tokens'] = 392
        result = self.scan([event(u)])
        self.assertEqual(result['unpriced_responses'], 1)

    def test_invalid_negative_partition_is_unpriced(self):
        result = self.scan([event(usage(10, c=20))])
        self.assertEqual(result['unpriced_responses'], 1)

    def test_unknown_budget_is_not_invented(self):
        result = self.scan([event(usage(100000))])
        self.assertIsNone(result['budget'])
        self.assertEqual(result['fast_usd'], 2.0)

    def test_model_change_prices_each_response_with_its_own_model(self):
        result = self.scan([event(usage(100000)),
                            dict(type='turn_context', payload=dict(model='unknown-model')),
                            event(usage(200000), usage(100000))])
        self.assertEqual(result['standard_usd'], 1.0)
        self.assertEqual(result['unpriced_responses'], 1)

    def test_unknown_then_known_tier_stays_unknown_without_losing_usage(self):
        result = self.scan([event(usage(100000)),
                            dict(type='turn_context', payload=dict(model='gpt-6-astra', service_tier='default')),
                            event(usage(200000), usage(100000))])
        self.assertIsNone(result['estimated_usd'])
        self.assertEqual(result['priced_responses'], 2)
        self.assertEqual(result['unpriced_responses'], 0)

    def test_token_value_never_claims_actual_charges_or_remaining_credit(self):
        result = self.scan([event(usage(100000))], tier='standard')
        self.assertIsNone(result['actual_charged_usd'])
        self.assertIsNone(result['account_credit_balance_usd'])

    def test_dashboard_spend_is_retained_with_its_user_provided_window(self):
        result = self.scan([event(usage(100000))], tier='standard',
                           account_spend=8.29, account_window='last 7 days')
        self.assertEqual(result['actual_charged_usd'], 8.29)
        self.assertEqual(result['actual_charged_window'], 'last 7 days')
        self.assertNotEqual(result['actual_charged_usd'], result['estimated_usd'])

    def test_nonpositive_dashboard_spend_is_rejected(self):
        with self.assertRaises(ValueError):
            self.scan([event(usage(100000))], account_spend=-.01)


if __name__ == '__main__':
    unittest.main()
