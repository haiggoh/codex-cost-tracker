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


if __name__ == '__main__':
    unittest.main()
