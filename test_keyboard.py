"""UPower backlight tests; no real keyboard settings are changed."""
import unittest
from unittest.mock import patch

import keyboard
from service import DashboardService


class KeyboardTests(unittest.TestCase):
    def test_read_supported_levels_and_off(self):
        with patch.object(keyboard, 'command', side_effect=[('i 2', None), ('i 0', None)]) as command:
            self.assertEqual(keyboard.status(), dict(available=True, brightness=0, maximum=2, error=None))
            self.assertTrue(all('SetBrightness' not in c.args for c in command.call_args_list))

    def test_missing_service_and_invalid_readings_remain_unavailable(self):
        for responses in [[(None, 'ServiceUnknown')], [('i 0', None)], [('i -1', None)],
                          [('not an integer', None)], [('i 2', None), ('i 3', None)],
                          [('i 2', None), ('i -1', None)]]:
            with self.subTest(responses=responses), patch.object(keyboard, 'command', side_effect=responses):
                result = keyboard.status()
                self.assertFalse(result['available'])
                self.assertIsNone(result['brightness'])
                self.assertTrue(result['error'])

    def test_invalid_inputs_never_write(self):
        for value in [None, True, False, '1', 1.5, [], {}, -1, 3]:
            with self.subTest(value=value), patch.object(keyboard, 'command', side_effect=[('i 2', None), ('i 1', None)]) as command:
                with self.assertRaises(ValueError):
                    keyboard.set_brightness(value)
                self.assertTrue(all('SetBrightness' not in c.args for c in command.call_args_list))

    def test_set_uses_typed_dbus_and_verifies_readback(self):
        replies = [('i 2', None), ('i 0', None), ('', None), ('i 2', None), ('i 2', None)]
        with patch.object(keyboard, 'command', side_effect=replies) as command:
            self.assertEqual(keyboard.set_brightness(2)['brightness'], 2)
            self.assertEqual(command.call_args_list[2].args[-3:], ('SetBrightness', 'i', '2'))

    def test_failed_or_ignored_write_is_not_reported_as_success(self):
        for last in [[(None, 'AccessDenied')], [('', None), ('i 2', None), ('i 0', None)]]:
            service = DashboardService()
            with patch.object(keyboard, 'command', side_effect=[('i 2', None), ('i 0', None)] + last):
                with self.assertRaises(RuntimeError):
                    service.run('keyboard', {'brightness': 2})
                self.assertFalse(service.events[-1]['ok'])
                self.assertFalse(service.busy)

    def test_service_serializes_keyboard_changes_and_records_success(self):
        service = DashboardService()
        with service.action_lock, patch.object(keyboard, 'set_brightness') as setter:
            with self.assertRaises(RuntimeError):
                service.run('keyboard', {'brightness': 1})
            setter.assert_not_called()
        with patch.object(keyboard, 'set_brightness', return_value={'brightness': 1, 'maximum': 2}):
            self.assertIn('1/2', service.run('keyboard', {'brightness': 1})['message'])
            self.assertTrue(service.events[-1]['ok'])


if __name__ == '__main__':
    unittest.main()
