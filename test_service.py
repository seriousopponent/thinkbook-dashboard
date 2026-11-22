"""Tests that preserve machine state while exercising the desktop bridge service."""
import getpass
from pathlib import Path
import threading
import unittest
from unittest.mock import patch

import hardware
from service import DashboardService


class ServiceTests(unittest.TestCase):
    def test_invalid_action_and_mode_never_execute(self):
        service = DashboardService()
        with patch.object(hardware, 'command', side_effect=AssertionError('Command executed')):
            for action, payload in [('shell', {'cmd': 'echo no'}), ('graphics', {'mode': 'bad'}),
                                    ('power', {'mode': 'bad'}), ('reboot', {})]:
                with self.subTest(action=action), self.assertRaises(ValueError):
                    service.run(action, payload)
        self.assertFalse(service.busy)

    def test_mutations_are_serialized_and_error_releases_lock(self):
        service = DashboardService()
        entered, release = threading.Event(), threading.Event()

        def slow_switch(_mode):
            entered.set()
            release.wait(timeout=2)
            return None, {'mode': 'hybrid'}

        with patch.object(hardware, 'set_graphics_mode', side_effect=slow_switch), \
                patch.object(hardware, 'command', side_effect=AssertionError('Concurrent command')):
            worker = threading.Thread(target=service.run, args=('graphics', {'mode': 'hybrid'}))
            worker.start()
            self.assertTrue(entered.wait(timeout=1))
            with self.assertRaisesRegex(RuntimeError, 'Başka bir ayar'):
                service.run('power', {'mode': 'battery'})
            release.set()
            worker.join(timeout=2)
            self.assertFalse(worker.is_alive())
        self.assertFalse(service.busy)

    def test_power_change_requires_verification(self):
        service = DashboardService()
        with patch.object(hardware, 'command', return_value=('', None)), \
                patch.object(hardware, 'power_status', return_value=('Balanced', None)):
            with self.assertRaisesRegex(RuntimeError, 'doğrulanamadı'):
                service.run('power', {'mode': 'battery'})
            self.assertFalse(service.events[-1]['ok'])
            self.assertFalse(service.busy)

    def test_regular_status_never_reads_nvidia_telemetry(self):
        service = DashboardService()
        with patch.object(hardware, 'gpu_telemetry', side_effect=AssertionError('GPU woke')):
            snapshot = service.run('status')
            self.assertIn('gpu', snapshot)
            self.assertIn('battery', snapshot)
            self.assertIn('reboot_required', snapshot['graphics'])

    def test_diagnostics_redact_user_paths_even_inside_error_messages(self):
        service = DashboardService()
        with patch.object(service, 'status', return_value={'error': f'{Path.home()}/helper failed for {getpass.getuser()}'}):
            output = service.run('diagnostics')['text']
        self.assertNotIn(str(Path.home()), output)
        self.assertNotIn(getpass.getuser(), output)


if __name__ == '__main__':
    unittest.main()
