"""Regression checks for power-safe monitoring and deferred graphics switches."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import hardware


class GraphicsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def write(self, name, value):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value)
        return path

    def test_background_monitor_never_invokes_gpu_tools(self):
        gpu = "sys/bus/pci/devices/0000:01:00.0/"
        self.write(gpu + "vendor", "0x10de")
        self.write(gpu + "class", "0x030000")
        self.write(gpu + "power/control", "auto")
        with patch.object(hardware.subprocess, "run", side_effect=AssertionError("GPU was probed")):
            for state in ("suspended", "active", "suspending", "resuming"):
                with self.subTest(state=state):
                    self.write(gpu + "power/runtime_status", state)
                    self.assertEqual(hardware.gpu_status(self.root / "sys")[0]["state"], state)
            self.assertEqual(hardware.gpu_status(self.root / "missing"), [])

    def test_saved_integrated_mode_is_not_misreported_as_compute_before_reboot(self):
        self.write("etc/prime-discrete", "off\n")
        self.write("etc/modprobe.d/system76-power.conf", "blacklist nvidia\nblacklist nvidia-drm\n")
        self.write("proc/stat", "cpu 1 2 3 4\nbtime 100\n")
        with patch.object(hardware, "command", return_value=("compute", None)):
            result = hardware.graphics_status(self.root / "etc", self.root / "proc")
        self.assertEqual(result["mode"], "integrated")
        self.assertEqual(result["reported"], "compute")
        self.assertTrue(result["reboot_required"])

    def test_compute_mode_is_distinct_from_integrated(self):
        self.write("etc/prime-discrete", "off\n")
        self.write("etc/modprobe.d/system76-power.conf", "blacklist nvidia-drm\nblacklist nvidia-modeset\n")
        with patch.object(hardware, "command", return_value=("compute", None)):
            self.assertEqual(hardware.graphics_status(self.root / "etc", self.root / "proc")["mode"], "compute")

    def test_reboot_banner_clears_after_boot_and_handles_missing_boot_time(self):
        prime = self.write("etc/prime-discrete", "on-demand\n")
        os.utime(prime, (50, 50))
        self.write("proc/stat", "btime 100\n")
        with patch.object(hardware, "command", return_value=("hybrid", None)):
            self.assertFalse(hardware.graphics_status(self.root / "etc", self.root / "proc")["reboot_required"])
            self.assertIsNone(hardware.graphics_status(self.root / "etc", self.root / "missing")["reboot_required"])

    def test_switch_allows_initramfs_time_and_verifies_saved_mode(self):
        with patch.object(hardware, "command", return_value=("", None)) as command, \
                patch.object(hardware, "graphics_status", return_value={"mode": "integrated"}):
            error, _ = hardware.set_graphics_mode("integrated")
            self.assertIsNone(error)
            self.assertGreaterEqual(command.call_args.kwargs["timeout"], 120)
            error, _ = hardware.set_graphics_mode("hybrid")
            self.assertIsNotNone(error)

    def test_timeout_is_not_reported_as_a_success_even_if_config_changed(self):
        with patch.object(hardware.subprocess, "run", side_effect=subprocess.TimeoutExpired("system76-power", 180)), \
                patch.object(hardware, "graphics_status", return_value={"mode": "hybrid"}):
            error, _ = hardware.set_graphics_mode("hybrid")
            self.assertIn("timed out", error)

    def test_invalid_modes_do_not_run_commands(self):
        with patch.object(hardware, "command", side_effect=AssertionError("Command ran")):
            with self.assertRaises(ValueError):
                hardware.set_graphics_mode("unsupported")


if __name__ == "__main__":
    unittest.main()
