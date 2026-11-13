from pathlib import Path
import tempfile
import unittest
from al_results.instance import InstanceLock


class InstanceTests(unittest.TestCase):
    def test_second_instance_cannot_change_current_checkpoint(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'collector.lock'
            with InstanceLock(path):
                with self.assertRaises(RuntimeError):
                    with InstanceLock(path):
                        self.fail('Second instance should not start')
            with InstanceLock(path):
                pass
