"""Unprivileged Linux hardware probes."""
import csv
import os
from pathlib import Path
import re
import subprocess

SYS = Path("/sys")
PROFILES = {"battery": "Battery Life", "balanced": "Balanced", "performance": "High Performance"}
GPU_FIELDS = "name,temperature.gpu,utilization.gpu,memory.used,memory.total,driver_version"
GRAPHICS_MODES = {
    "hybrid": ("Hibrit · önerilen", "Günlük işlerde Intel kullanılır; NVIDIA gerektiğinde devreye girer."),
    "integrated": ("Yalnızca Intel · pil tasarrufu", "NVIDIA devre dışı kalır. NVIDIA'ya bağlı HDMI ve harici ekran çıkışları kullanılamayabilir."),
    "nvidia": ("NVIDIA · yüksek performans", "NVIDIA sürekli kullanılabilir durumda kalır; pil tüketimi artar."),
    "compute": ("Hesaplama · Intel + CUDA", "Görüntüyü Intel işler; NVIDIA hesaplama işleri için kullanılabilir kalır."),
}


def read(path):
    try:
        return path.read_text().strip() or None
    except OSError:
        return None


def command(*args, timeout=4):
    try:
        result = subprocess.run(args, capture_output=True, text=True, errors="replace",
                                timeout=timeout, env={**os.environ, "LC_ALL": "C"})
    except FileNotFoundError:
        return None, f"{args[0]} is not installed."
    except subprocess.TimeoutExpired:
        return None, f"{args[0]} timed out."
    except OSError as error:
        return None, str(error)
    if result.returncode:
        return None, (result.stderr or result.stdout).strip() or f"Exit {result.returncode}"
    return result.stdout.strip(), None


def cpu_times(path=Path("/proc/stat")):
    line = read(path)
    if line:
        try:
            _, *fields = line.splitlines()[0].split()
            counters = list(map(int, fields[:8]))
            if len(counters) >= 4:
                return sum(counters), sum(counters[3:5])
        except ValueError:
            pass
    return None


def cpu_usage(previous, current):
    if previous and current:
        total = current[0] - previous[0]
        idle = current[1] - previous[1]
        if total > 0 and 0 <= idle <= total:
            return round(100 * (total - idle) / total)
    return None


def temperature(sys):
    for device in sorted((sys / "class/hwmon").glob("hwmon*")):
        if read(device / "name") != "coretemp":
            continue
        for label in sorted(device.glob("temp*_label")):
            if (read(label) or "").startswith("Package id"):
                try:
                    return round(int(read(label.with_name(label.name.replace("_label", "_input")))) / 1000)
                except (TypeError, ValueError):
                    continue
    return None


def local_status(sys=SYS):
    acpi = sys / "firmware/acpi"
    profile = read(acpi / "platform_profile")
    choices = read(acpi / "platform_profile_choices")
    if not profile:
        for device in sorted((sys / "class/platform-profile").glob("platform-profile-*")):
            if read(device / "name") in ("ideapad", "ideapad-laptop"):
                profile, choices = read(device / "profile"), read(device / "choices")
                break
    supplies = sorted((sys / "class/power_supply").glob("*"))
    batteries = [
        (device.name, *(read(device / key) for key in (
            "capacity", "status", "charge_types", "charge_control_start_threshold",
            "charge_control_end_threshold")))
        for device in supplies if read(device / "type") == "Battery"
        and read(device / "present") != "0"
    ]
    modes = [read(path) for path in
             (sys / "bus/platform/drivers/ideapad_acpi").glob("*/conservation_mode")]
    conservation = {"1": "On", "0": "Off"}.get(next((mode for mode in modes if mode in ("0", "1")), None))
    return profile, choices, batteries, conservation, temperature(sys)


def power_status():
    profile, error = command("system76-power", "profile")
    if profile:
        profile = profile.splitlines()[0].removeprefix("Power Profile: ").strip()
        profile = PROFILES.get(profile.casefold(), profile)
    return profile, error


def graphics_status(config=Path("/etc"), proc=Path("/proc")):
    """Read the saved mode separately from the driver's current-session report."""
    reported, error = command("system76-power", "graphics")
    prime = config / "prime-discrete"
    modprobe = config / "modprobe.d/system76-power.conf"
    setting = read(prime)
    mode = {"on-demand": "hybrid", "on": "nvidia"}.get(setting, reported)
    if setting == "off":
        # The CLI reports 'compute' before an integrated-mode reboot because
        # the NVIDIA module is still loaded. The saved config is authoritative.
        blocked = re.search(r"^\s*blacklist\s+nvidia\s*(?:#.*)?$", read(modprobe) or "", re.M)
        mode = "integrated" if blocked else "compute"
    boot = re.search(r"^btime (\d+)$", read(proc / "stat") or "", re.M)
    pending = None
    if boot:
        try:
            pending = any(path.exists() and path.stat().st_mtime > int(boot[1])
                          for path in (prime, modprobe))
        except OSError:
            pass
    return dict(mode=mode, reported=reported, reboot_required=pending, error=error)


def set_graphics_mode(mode):
    if mode not in GRAPHICS_MODES:
        raise ValueError("Unknown graphics mode")
    # Updating the initramfs takes longer than an ordinary status query.
    _, error = command("system76-power", "graphics", mode, timeout=180)
    status = graphics_status()
    if not error and status["mode"] != mode:
        error = "İstenen grafik modu kaydedilmiş olarak doğrulanamadı."
    return error, status


def gpu_status(sys=SYS):
    """Read only sysfs metadata; never wake the GPU to obtain telemetry."""
    devices = []
    for device in sorted((sys / "bus/pci/devices").glob("*")):
        if read(device / "vendor") != "0x10de" or not (read(device / "class") or "").startswith("0x03"):
            continue
        devices.append(dict(pci=device.name, state=read(device / "power/runtime_status"),
                            control=read(device / "power/control")))
    return devices


def gpu_telemetry():
    """Explicit one-shot measurement: this may wake a sleeping GPU."""
    output, error = command("nvidia-smi", f"--query-gpu={GPU_FIELDS}", "--format=csv,noheader,nounits")
    rows = [row for row in csv.reader((output or "").splitlines(), skipinitialspace=True)
            if len(row) == 6]
    return rows, error or (None if rows else "No NVIDIA telemetry returned.")
