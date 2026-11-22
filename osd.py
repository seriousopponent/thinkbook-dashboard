#!/usr/bin/python3
"""Session-wide, read-only Lenovo profile observer and Wayland OSD."""
import ctypes
from pathlib import Path
import sys
import time

import hardware


def load_layer_shell():
    import gi
    vendor = Path(__file__).resolve().parent / "vendor"
    if vendor.exists():
        gi.__path__.append(str(vendor))
        ctypes.CDLL(str(vendor / "libgtk-layer-shell.so.0"), mode=ctypes.RTLD_GLOBAL)
        gi.require_version("GIRepository", "2.0")
        from gi.repository import GIRepository
        GIRepository.Repository.prepend_search_path(str(vendor))
    gi.require_version("GtkLayerShell", "0.1")
    from gi.repository import GtkLayerShell
    return GtkLayerShell


def read_profile():
    profile = hardware.read(hardware.SYS / "firmware/acpi/platform_profile")
    if profile:
        return profile
    for device in sorted((hardware.SYS / "class/platform-profile").glob("platform-profile-*")):
        if hardware.read(device / "name") in ("ideapad", "ideapad-laptop"):
            return hardware.read(device / "profile")
    return None


class ProfileObserver:
    def __init__(self):
        self.previous = None

    def update(self, current):
        changed = bool(current and self.previous and current != self.previous)
        self.previous = current
        return changed


def main():
    import gi
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gio, GLib, Gtk
    Layer = load_layer_shell()
    gi.require_foreign("cairo")
    import cairo

    class ProfileOSD(Gtk.Application):
        def __init__(self):
            super().__init__(application_id="io.github.thinkbook.ProfileOSD",
                             flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
            self.observer = ProfileObserver()
            self.window = None
            self.animation = None
            self.connect("startup", self.start)
            self.connect("command-line", self.command_line)

        def start(self, _app):
            self.hold()
            self.observer.update(read_profile())
            GLib.timeout_add(250, self.poll)

        def command_line(self, _app, command):
            if "--preview" in command.get_arguments():
                self.show_profile(read_profile() or "unavailable")
            return 0

        def poll(self):
            current = read_profile()
            if self.observer.update(current):
                self.show_profile(current)
            return True

        def create_window(self):
            if not Layer.is_supported():
                raise RuntimeError("The session does not support Wayland layer shell.")
            self.window = Gtk.Window(title="Lenovo firmware profile")
            self.window.set_decorated(False)
            self.window.set_resizable(False)
            self.window.set_accept_focus(False)
            self.window.set_app_paintable(True)
            screen = self.window.get_screen()
            visual = screen.get_rgba_visual()
            if visual:
                self.window.set_visual(visual)
            Layer.init_for_window(self.window)
            Layer.set_namespace(self.window, "thinkbook-profile-osd")
            Layer.set_layer(self.window, Layer.Layer.OVERLAY)
            Layer.set_keyboard_mode(self.window, Layer.KeyboardMode.NONE)
            Layer.set_anchor(self.window, Layer.Edge.BOTTOM, True)
            Layer.set_margin(self.window, Layer.Edge.BOTTOM, 80)
            Layer.set_exclusive_zone(self.window, -1)
            self.window.connect("realize", lambda window: window.get_window().input_shape_combine_region(cairo.Region(), 0, 0))
            provider = Gtk.CssProvider()
            provider.load_from_data(b"""
                window { background-color: transparent; }
                .profile-osd { background-color: @theme_bg_color; color: @theme_fg_color;
                    border: 1px solid alpha(@theme_fg_color, .20); border-radius: 18px;
                    padding: 20px 32px; }
                .profile-title { font-size: 20px; font-weight: bold; }
                .profile-caption { font-size: 12px; opacity: .72; }
            """)
            Gtk.StyleContext.add_provider_for_screen(screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
            box = Gtk.Box(spacing=18)
            box.get_style_context().add_class("profile-osd")
            self.icon = Gtk.Image()
            self.icon.set_pixel_size(40)
            box.pack_start(self.icon, False, False, 0)
            text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            caption = Gtk.Label(label="Lenovo · Fn+Q", xalign=0)
            caption.get_style_context().add_class("profile-caption")
            self.title = Gtk.Label(xalign=0)
            self.title.get_style_context().add_class("profile-title")
            text.pack_start(caption, False, False, 0)
            text.pack_start(self.title, False, False, 0)
            box.pack_start(text, False, False, 0)
            self.window.add(box)

        def show_profile(self, profile):
            if not self.window:
                self.create_window()
            names = {"low-power": "Güç tasarrufu", "balanced": "Dengeli",
                     "performance": "Performans", "quiet": "Sessiz",
                     "unavailable": "Profil okunamıyor"}
            icons = {"low-power": "power-profile-power-saver-symbolic",
                     "balanced": "power-profile-balanced-symbolic",
                     "performance": "power-profile-performance-symbolic"}
            self.title.set_text(names.get(profile, profile.replace("-", " ").title()))
            self.icon.set_from_icon_name(icons.get(profile, "computer-symbolic"), Gtk.IconSize.DIALOG)
            if self.animation:
                GLib.source_remove(self.animation)
            self.started = time.monotonic()
            self.animate = Gtk.Settings.get_default().get_property("gtk-enable-animations")
            Gtk.Widget.set_opacity(self.window, 0 if self.animate else 1)
            self.window.show_all()
            self.animation = GLib.timeout_add(16 if self.animate else 2400, self.frame)

        def frame(self):
            elapsed = time.monotonic() - self.started
            if elapsed >= 2.4:
                self.window.hide()
                self.animation = None
                return False
            opacity = min(1, elapsed / .16, (2.4 - elapsed) / .22) if self.animate else 1
            Gtk.Widget.set_opacity(self.window, max(0, opacity))
            return True

    return ProfileOSD().run(sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())
