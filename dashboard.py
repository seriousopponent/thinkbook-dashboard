#!/usr/bin/python3
"""ThinkBook Dashboard GTK application."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess

import hardware


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe", action="store_true", help="Print hardware readings as JSON.")
    if parser.parse_args().probe:
        print(json.dumps(dict(local=hardware.local_status(), power=hardware.power_status(),
                              graphics=hardware.graphics_status(), nvidia=hardware.gpu_status()), indent=2))
        return
    launch()


def launch():
    import gi
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gio, GLib, Gtk

    app = Gtk.Application(application_id="io.github.thinkbook.Dashboard")

    class Dashboard(Gtk.ApplicationWindow):
        def __init__(self):
            super().__init__(application=app, title="ThinkBook Dashboard", default_width=820,
                             default_height=670)
            self.executor = ThreadPoolExecutor(max_workers=3)
            self.pending = set()
            self.timers = []
            self.previous_profile = None
            self.previous_cpu = None
            self.closed = False
            self.changing_power = False
            self.changing_graphics = False
            self.graphics_state = None
            self.flash_timer = None
            self.css = Gtk.CssProvider()
            self.css.load_from_data(b"""
                .card { padding: 18px; border: 1px solid alpha(@theme_fg_color, .16);
                        border-radius: 12px; background-color: alpha(@theme_fg_color, .04);
                        transition: background-color 320ms ease-out; }
                .card.profile-flash { background-color: alpha(@theme_selected_bg_color, .40); }
                .section { font-weight: bold; }
                .reading { font-size: 17px; font-weight: bold; }
                .detail { opacity: .78; }
                .model { font-size: 24px; font-weight: bold; }
            """)
            Gtk.StyleContext.add_provider_for_screen(self.get_screen(), self.css,
                                                     Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
            header = Gtk.HeaderBar(title="ThinkBook Dashboard", show_close_button=True)
            self.set_titlebar(header)
            refresh = Gtk.Button.new_from_icon_name("view-refresh-symbolic", Gtk.IconSize.BUTTON)
            refresh.set_tooltip_text("Refresh all readings")
            refresh.get_accessible().set_name("Refresh all readings")
            refresh.connect("clicked", lambda *_: self.refresh())
            header.pack_end(refresh)

            scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
            self.add(scroll)
            layout = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14, margin=22)
            scroll.add(layout)
            model = hardware.read(hardware.SYS / "class/dmi/id/product_version")
            layout.pack_start(self.label(model or "System dashboard", "model"), False, False, 0)
            preview = Gtk.Button(label="Fn+Q göstergesini dene")
            preview.set_halign(Gtk.Align.START)
            preview.connect("clicked", lambda *_: subprocess.Popen(
                ["/usr/bin/python3", str(Path(__file__).with_name("osd.py")), "--preview"],
                start_new_session=True))
            layout.pack_start(preview, False, False, 0)
            self.cards = {}
            for key, title in (
                ("graphics", "Grafik modu"), ("gpu", "NVIDIA güç durumu"),
                ("firmware", "Lenovo firmware profile"), ("power", "Pop!_OS power profile"),
                ("battery", "Battery"), ("cpu", "CPU"),
            ):
                card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=7)
                card.get_style_context().add_class("card")
                card.pack_start(self.label(title, "section"), False, False, 0)
                value = self.label("Reading…", "reading")
                detail = self.label("", "detail")
                card.pack_start(value, False, False, 0)
                card.pack_start(detail, False, False, 0)
                layout.pack_start(card, False, False, 0)
                self.cards[key] = card, value, detail

            self.graphics_controls = Gtk.Box(spacing=8)
            self.graphics_picker = Gtk.ComboBoxText()
            self.graphics_picker.get_accessible().set_name("Grafik modu seçimi")
            for key, (name, _description) in hardware.GRAPHICS_MODES.items():
                self.graphics_picker.append(key, name)
            self.graphics_picker.connect("changed", self.graphics_selection_changed)
            self.graphics_apply = Gtk.Button(label="Modu uygula")
            self.graphics_apply.connect("clicked", self.apply_graphics)
            self.graphics_controls.pack_start(self.graphics_picker, False, False, 0)
            self.graphics_controls.pack_start(self.graphics_apply, False, False, 0)
            self.graphics_controls.set_sensitive(False)
            self.graphics_description = self.label("", "detail")
            self.graphics_feedback = self.label("", "detail")
            self.graphics_restart = self.label("", "detail")
            for widget in (self.graphics_controls, self.graphics_description,
                           self.graphics_restart, self.graphics_feedback):
                self.cards["graphics"][0].pack_start(widget, False, False, 0)

            self.telemetry_button = Gtk.Button(label="Ayrıntıları bir kez ölç")
            self.telemetry_button.set_halign(Gtk.Align.START)
            self.telemetry_button.set_tooltip_text("Sıcaklık ve kullanım ölçümü NVIDIA'yı geçici olarak uyandırabilir.")
            self.telemetry_button.connect("clicked", self.measure_gpu)
            self.cards["gpu"][0].pack_start(self.label(
                "Durum kartı uyandırmadan izlenir. Ayrıntılı ölçüm kartı geçici olarak uyandırabilir.",
                "detail"), False, False, 0)
            self.cards["gpu"][0].pack_start(self.telemetry_button, False, False, 0)
            self.telemetry_detail = self.label("", "detail")
            self.cards["gpu"][0].pack_start(self.telemetry_detail, False, False, 0)

            firmware_controls = Gtk.Box(spacing=8)
            self.firmware_picker = Gtk.ComboBoxText()
            self.firmware_picker.get_accessible().set_name("Lenovo firmware profile")
            choices = hardware.read(hardware.SYS / "firmware/acpi/platform_profile_choices") or ""
            for profile in choices.split():
                self.firmware_picker.append(profile, profile.replace("-", " ").title())
            self.firmware_picker.set_active_id(hardware.read(hardware.SYS / "firmware/acpi/platform_profile"))
            firmware_controls.pack_start(self.firmware_picker, False, False, 0)
            firmware_apply = Gtk.Button(label="Apply…")
            firmware_apply.set_tooltip_text("Set the firmware profile using system authentication")
            firmware_apply.connect("clicked", self.apply_firmware)
            firmware_controls.pack_start(firmware_apply, False, False, 0)
            firmware_controls.set_sensitive(bool(choices))
            self.firmware_controls = firmware_controls
            self.firmware_feedback = self.label("", "detail")
            self.cards["firmware"][0].pack_start(firmware_controls, False, False, 0)
            self.cards["firmware"][0].pack_start(self.firmware_feedback, False, False, 0)

            controls = Gtk.Box(spacing=8)
            self.profile_picker = Gtk.ComboBoxText()
            self.profile_picker.get_accessible().set_name("Pop!_OS power profile")
            for key, name in hardware.PROFILES.items():
                self.profile_picker.append(key, name)
            self.apply_button = Gtk.Button(label="Apply")
            self.apply_button.connect("clicked", self.apply_profile)
            controls.pack_start(self.profile_picker, False, False, 0)
            controls.pack_start(self.apply_button, False, False, 0)
            controls.set_sensitive(False)
            self.controls = controls
            self.feedback = self.label("", "detail")
            self.cards["power"][0].pack_start(controls, False, False, 0)
            self.cards["power"][0].pack_start(self.feedback, False, False, 0)
            self.connect("destroy", self.shutdown)
            self.connect("delete-event", self.before_close)
            self.show_all()
            self.refresh()
            self.timers.extend([
                GLib.timeout_add(750, self.update_local),
                GLib.timeout_add_seconds(10, self.refresh_power),
                GLib.timeout_add_seconds(10, self.refresh_graphics),
                GLib.timeout_add_seconds(5, self.refresh_gpu),
            ])

        @staticmethod
        def label(value, style):
            label = Gtk.Label(label=value, xalign=0, wrap=True, selectable=True)
            label.get_style_context().add_class(style)
            return label

        def set_card(self, key, value, detail=""):
            _, reading, description = self.cards[key]
            reading.set_text(value)
            description.set_text(detail)

        def refresh(self):
            self.update_local()
            self.refresh_power()
            self.refresh_graphics()
            self.refresh_gpu()

        def update_local(self):
            profile, choices, batteries, conservation, temp = hardware.local_status()
            display = profile.replace("-", " ").title() if profile else "Unavailable"
            detail = "Select a firmware profile below. Fn+Q requires working BIOS hotkey support." if profile else "Linux firmware profile interface unavailable."
            if choices:
                detail += " Available: " + ", ".join(choices.split())
            self.set_card("firmware", display, detail)
            if profile and self.previous_profile and profile != self.previous_profile:
                self.animate_profile()
            self.previous_profile = profile

            summaries, details = [], []
            for name, percent, status, types, start, end in batteries:
                charge = f"{percent}%" if percent is not None else "Charge unavailable"
                summaries.append(f"{name} · {charge} · {status or 'Status unavailable'}")
                if types:
                    details.append(f"{name} charge modes: {types}")
                if start or end:
                    details.append(f"{name} thresholds: start {start or '—'}%, end {end or '—'}%")
            details.append(f"Lenovo conservation mode: {conservation or 'Interface unavailable'}")
            self.set_card("battery", "\n".join(summaries) or "Battery unavailable", "\n".join(details))

            current = hardware.cpu_times()
            usage = hardware.cpu_usage(self.previous_cpu, current)
            if current != self.previous_cpu:
                self.previous_cpu = current
            load = f"{usage}% utilization" if usage is not None else "Utilization unavailable"
            thermal = f"CPU package: {temp} °C" if temp is not None else "CPU package sensor unavailable."
            self.set_card("cpu", load, thermal)
            return True

        def animate_profile(self):
            if not self.get_settings().get_property("gtk-enable-animations"):
                return
            if self.flash_timer:
                GLib.source_remove(self.flash_timer)
            self.cards["firmware"][0].get_style_context().add_class("profile-flash")
            self.flash_timer = GLib.timeout_add(460, self.clear_flash)

        def clear_flash(self):
            self.cards["firmware"][0].get_style_context().remove_class("profile-flash")
            self.flash_timer = None
            return False

        def submit(self, key, work, display):
            if key in self.pending:
                return
            self.pending.add(key)

            def deliver(result):
                self.pending.discard(key)
                if not self.closed:
                    display(result.result())
                return False

            self.executor.submit(work).add_done_callback(lambda result: GLib.idle_add(deliver, result))

        def refresh_power(self):
            if not self.changing_power:
                self.apply_button.set_sensitive(False)
                self.submit("power", hardware.power_status, self.display_power)
            return True

        def display_power(self, result):
            if self.changing_power:
                return
            profile, error = result
            self.set_card("power", profile or "Unavailable", error or "Managed by system76-power.")
            self.controls.set_sensitive(bool(profile))
            self.apply_button.set_sensitive(True)
            if not self.profile_picker.get_active_id() and profile:
                for key, name in hardware.PROFILES.items():
                    if profile.casefold() in (key, name.casefold()):
                        self.profile_picker.set_active_id(key)
                        break

        def refresh_graphics(self):
            if not self.changing_graphics:
                self.submit("graphics", hardware.graphics_status, self.display_graphics)
            return True

        def display_graphics(self, status):
            if self.changing_graphics:
                return
            previous = self.graphics_state
            self.graphics_state = status
            mode = status["mode"]
            name = hardware.GRAPHICS_MODES.get(mode, (mode or "Okunamıyor", ""))[0]
            self.set_card("graphics", "Seçili mod: " + name,
                          status["error"] or "Modu seçip uygula. Grafik modu değişiklikleri yeniden başlatma gerektirir.")
            pending = status["reboot_required"]
            self.graphics_restart.set_text(
                "Yeniden başlatma gerekiyor: ayar bu oturumda değişti. Çalışmalarını kaydedip sistem menüsünden yeniden başlat."
                if pending else ("Yeniden başlatma durumu okunamadı; mod değiştirdiysen yeniden başlat."
                                 if pending is None else "Yeniden başlatma bekleyen grafik ayarı yok."))
            selection = self.graphics_picker.get_active_id()
            if not selection or (previous and selection == previous["mode"]):
                self.graphics_picker.set_active_id(mode)
            self.graphics_controls.set_sensitive(mode in hardware.GRAPHICS_MODES and not status["error"])
            self.graphics_selection_changed()

        def graphics_selection_changed(self, *_):
            selection = self.graphics_picker.get_active_id()
            self.graphics_description.set_text(hardware.GRAPHICS_MODES.get(selection, ("", ""))[1])
            self.graphics_apply.set_sensitive(bool(self.graphics_state) and
                                               selection in hardware.GRAPHICS_MODES and
                                               selection != self.graphics_state["mode"] and
                                               not self.changing_graphics)

        def apply_graphics(self, _button):
            selection = self.graphics_picker.get_active_id()
            if (selection not in hardware.GRAPHICS_MODES or self.changing_graphics
                    or "graphics" in self.pending or not self.graphics_state
                    or selection == self.graphics_state["mode"]):
                return
            self.changing_graphics = True
            self.graphics_controls.set_sensitive(False)
            self.graphics_feedback.set_text("Mod uygulanıyor; açılış ayarları hazırlanıyor… Bu işlem biraz sürebilir.")

            def finished(result):
                error, status = result
                self.changing_graphics = False
                self.display_graphics(status)
                self.graphics_feedback.set_text(
                    "İşlem tamamlanamadı: " + error if error else
                    "Mod kaydedildi. Değişikliğin tamamlanması için bilgisayarı yeniden başlat.")
                self.refresh_gpu()

            self.submit("graphics-change", lambda: hardware.set_graphics_mode(selection), finished)

        def before_close(self, *_):
            if self.changing_graphics:
                self.graphics_feedback.set_text("Grafik ayarı hâlâ uygulanıyor. İşlem tamamlanınca pencereyi kapatabilirsin.")
                return True
            return False

        def apply_firmware(self, _button):
            profile = self.firmware_picker.get_active_id()
            if not profile or "firmware-change" in self.pending:
                return
            self.firmware_controls.set_sensitive(False)
            self.firmware_feedback.set_text("Sistem kimlik doğrulaması bekleniyor…")

            def work():
                try:
                    result = subprocess.run(
                        ["pkexec", "/usr/bin/python3", "-I",
                         str(Path(__file__).with_name("set_firmware_profile.py")), profile],
                        capture_output=True, text=True, timeout=120)
                    return result.returncode, (result.stderr or result.stdout).strip()
                except (OSError, subprocess.TimeoutExpired) as error:
                    return 1, str(error)

            def finished(result):
                code, message = result
                self.firmware_controls.set_sensitive(True)
                self.firmware_feedback.set_text(message if code else "Firmware profili uygulandı.")
                self.update_local()

            self.submit("firmware-change", work, finished)

        def apply_profile(self, _button):
            selection = self.profile_picker.get_active_id()
            if selection not in hardware.PROFILES or self.changing_power or "power" in self.pending:
                return
            self.changing_power = True
            self.controls.set_sensitive(False)
            self.feedback.set_text("Applying profile…")

            def change():
                _, error = hardware.command("system76-power", "profile", selection)
                return error, hardware.power_status()

            def finished(result):
                error, status = result
                self.changing_power = False
                self.display_power(status)
                verified = status[0] == hardware.PROFILES[selection]
                self.feedback.set_text(error or ("Profile applied." if verified else
                                                 "The requested profile could not be verified."))

            self.submit("change", change, finished)

        def refresh_gpu(self):
            self.submit("gpu", hardware.gpu_status, self.display_gpu)
            return True

        def display_gpu(self, result):
            states = {"active": "Aktif", "suspended": "Uykuda", "suspending": "Uykuya geçiyor",
                      "resuming": "Uyanıyor", "unsupported": "Uyku durumu desteklenmiyor"}
            titles, details = [], []
            for device in result:
                titles.append("NVIDIA · " + states.get(device["state"], "Durum okunamıyor"))
                if device["control"] == "on":
                    details.append("Otomatik uyku kapalı. Hibrit moda yeni geçtiysen yeniden başlatman gerekiyor.")
                elif device["control"] == "auto":
                    details.append("Otomatik uyku açık." + (
                        " Kart kullanılmadığı için uykuda." if device["state"] == "suspended" else
                        " Bir uygulama veya bağlı ekran kartı aktif tutabilir."))
            self.set_card("gpu", "\n".join(titles) or "NVIDIA aygıtı görünmüyor", "\n".join(details))

        def measure_gpu(self, _button):
            if "telemetry" in self.pending:
                return
            self.telemetry_button.set_sensitive(False)
            self.telemetry_detail.set_text("Tek seferlik ölçüm alınıyor…")
            self.submit("telemetry", hardware.gpu_telemetry, self.display_telemetry)

        def display_telemetry(self, result):
            self.telemetry_button.set_sensitive(True)
            rows, error = result
            names, details = [], []
            for name, temp, load, used, total, driver in rows:
                names.append(name)
                metrics = []
                if temp.isdecimal():
                    metrics.append(f"{temp} °C")
                if load.isdecimal():
                    metrics.append(f"{load}% utilization")
                if used.isdecimal() and total.isdecimal():
                    metrics.append(f"{used} / {total} MiB VRAM")
                if driver and driver != "[N/A]":
                    metrics.append(f"driver {driver}")
                details.append(" · ".join(metrics) or "Metrics unavailable.")
            timestamp = GLib.DateTime.new_now_local().format("%H:%M:%S")
            self.telemetry_detail.set_text(error or
                f"Son ölçüm ({timestamp}, canlı değil): " + "\n".join(
                    f"{name} · {detail}" for name, detail in zip(names, details)))
            self.refresh_gpu()

        def shutdown(self, *_):
            self.closed = True
            for timer in self.timers:
                GLib.source_remove(timer)
            if self.flash_timer:
                GLib.source_remove(self.flash_timer)
            self.executor.shutdown(wait=False, cancel_futures=True)

    def activate(application):
        window = application.get_active_window() or Dashboard()
        window.present()

    app.connect("activate", activate)
    app.run([])


if __name__ == "__main__":
    main()
