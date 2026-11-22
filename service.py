"""Local, allowlisted dashboard operations. No HTTP listener or shell commands."""
from datetime import datetime
import getpass
import json
from pathlib import Path
import platform
import shutil
import subprocess
import threading
import time

import hardware

BASE = Path(__file__).resolve().parent


def number(path, divisor=1):
    try:
        return float(hardware.read(path)) / divisor
    except (TypeError, ValueError):
        return None


def battery_info(sys=hardware.SYS):
    supplies = sys / "class/power_supply"
    batteries = [p for p in sorted(supplies.glob("*"))
                 if hardware.read(p / "type") == "Battery" and hardware.read(p / "present") != "0"]
    online = any(hardware.read(p / "online") == "1" for p in supplies.glob("*"))
    if not batteries:
        return dict(present=False, online=online)
    device = batteries[0]
    full = number(device / "energy_full", 1_000_000)
    design = number(device / "energy_full_design", 1_000_000)
    energy = number(device / "energy_now", 1_000_000)
    watts = number(device / "power_now", 1_000_000)
    status = hardware.read(device / "status")
    return dict(present=True, online=online, percent=number(device / "capacity"), status=status,
                watts=watts, energy_wh=energy, full_wh=full, design_wh=design,
                health=round(100 * full / design, 1) if full and design else None,
                cycles=number(device / "cycle_count"),
                remaining_hours=round(energy / watts, 1) if energy and watts and status == "Discharging" else None)


class DashboardService:
    def __init__(self):
        self.previous_cpu = None
        self.last_metadata = 0
        self.metadata = {}
        self.action_lock = threading.Lock()
        self.status_lock = threading.Lock()
        self.events = []
        self.session_started = datetime.now().isoformat(timespec="seconds")

    @property
    def busy(self):
        return self.action_lock.locked()

    def status(self):
        with self.status_lock:
            if not self.metadata or (time.monotonic() - self.last_metadata > 20 and not self.busy):
                profile, error = hardware.power_status()
                key = next((k for k, v in hardware.PROFILES.items() if v == profile), None)
                self.metadata = dict(power=dict(mode=key, label=profile, error=error),
                                     graphics=hardware.graphics_status())
                self.last_metadata = time.monotonic()
            profile, choices, _batteries, conservation, temp = hardware.local_status()
            current = hardware.cpu_times()
            usage = hardware.cpu_usage(self.previous_cpu, current)
            self.previous_cpu = current
            mem = {}
            for line in (hardware.read(Path('/proc/meminfo')) or '').splitlines():
                key, _, value = line.partition(':')
                try:
                    mem[key] = int(value.split()[0])
                except (ValueError, IndexError):
                    pass
            total, available = mem.get('MemTotal'), mem.get('MemAvailable')
            cpu_name = next((line.split(':', 1)[1].strip() for line in
                             (hardware.read(Path('/proc/cpuinfo')) or '').splitlines()
                             if line.startswith('model name')), 'Intel işlemci')
            disk = shutil.disk_usage(Path.home())
            os_name = platform.freedesktop_os_release().get('PRETTY_NAME', 'Linux')
            return dict(timestamp=datetime.now().isoformat(timespec='seconds'),
                        session_started=self.session_started,
                        model=hardware.read(hardware.SYS / 'class/dmi/id/product_version') or 'ThinkBook',
                        os=os_name, kernel=platform.release(), cpu_name=cpu_name,
                        cpu=dict(usage=usage, temperature=temp),
                        memory=dict(total_gib=round(total / 1048576, 1) if total else None,
                                    used_gib=round((total - available) / 1048576, 1) if total and available else None,
                                    percent=round(100 * (total - available) / total) if total and available else None),
                        disk=dict(total_gib=round(disk.total / 1073741824), used_gib=round(disk.used / 1073741824),
                                  percent=round(100 * disk.used / disk.total)),
                        battery={**battery_info(), 'conservation': conservation},
                        firmware=dict(mode=profile, choices=(choices or '').split()),
                        gpu=hardware.gpu_status(), busy=self.busy,
                        events=list(self.events[-12:]), **self.metadata)

    def event(self, title, ok):
        self.events.append(dict(time=datetime.now().isoformat(timespec='seconds'), title=title, ok=ok))

    def run(self, action, payload=None):
        payload = payload or {}
        if not isinstance(payload, dict):
            raise ValueError('Geçersiz istek.')
        if action == 'status':
            return self.status()
        if action == 'telemetry':
            rows, error = hardware.gpu_telemetry()
            if error:
                raise RuntimeError(error)
            return dict(rows=rows, timestamp=datetime.now().isoformat(timespec='seconds'))
        if action == 'preview':
            subprocess.Popen(['/usr/bin/python3', str(BASE / 'osd.py'), '--preview'], start_new_session=True)
            return dict(message='Fn+Q göstergesi açıldı.')
        if action == 'diagnostics':
            snapshot = self.status()
            # Deliberately omit device serials, UUIDs, paths and user names.
            text = json.dumps(snapshot, ensure_ascii=False, indent=2)
            text = text.replace(str(Path.home()), '[ev klasörü]').replace(getpass.getuser(), '[kullanıcı]')
            return dict(text=text)
        if action not in ('graphics', 'power', 'firmware', 'reboot'):
            raise ValueError('Desteklenmeyen işlem.')
        if not self.action_lock.acquire(blocking=False):
            raise RuntimeError('Başka bir ayar uygulanıyor. Tamamlanmasını bekle.')
        try:
            selection = payload.get('mode')
            if action == 'graphics':
                if selection not in hardware.GRAPHICS_MODES:
                    raise ValueError('Geçersiz grafik modu.')
                error, _status = hardware.set_graphics_mode(selection)
                if error:
                    raise RuntimeError(error)
                message = 'Grafik modu kaydedildi. Yeniden başlattığında tamamen uygulanacak.'
            elif action == 'power':
                if selection not in hardware.PROFILES:
                    raise ValueError('Geçersiz güç profili.')
                _, error = hardware.command('system76-power', 'profile', selection, timeout=15)
                actual, check_error = hardware.power_status()
                if error or check_error or actual != hardware.PROFILES[selection]:
                    raise RuntimeError(error or check_error or 'Güç profili doğrulanamadı.')
                message = 'Güç profili uygulandı.'
            elif action == 'firmware':
                choices = hardware.local_status()[1] or ''
                if selection not in choices.split():
                    raise ValueError('Bu firmware profili desteklenmiyor.')
                _, error = hardware.command('pkexec', '/usr/bin/python3', '-I',
                                             str(BASE / 'set_firmware_profile.py'), selection, timeout=120)
                if error:
                    raise RuntimeError(error)
                message = 'Lenovo firmware profili uygulandı.'
            else:
                if payload.get('confirmed') is not True:
                    raise ValueError('Yeniden başlatma onayı eksik.')
                _, error = hardware.command('systemctl', 'reboot', timeout=15)
                if error:
                    raise RuntimeError(error)
                message = 'Bilgisayar yeniden başlatılıyor.'
            self.event(message, True)
            return dict(message=message)
        except Exception as error:
            self.event(str(error), False)
            raise
        finally:
            self.last_metadata = 0
            self.action_lock.release()
