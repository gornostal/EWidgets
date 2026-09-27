"""Loads the stylesheets and follows the OS light/dark preference.

Stylesheets use colours from a palette (@define-color). The light palette is
always loaded; the dark one sits a priority step above it while the OS prefers
dark, so its definitions win. The OS accent colour replaces @ew_accent from a
provider above both, together with @ew_accent_pair, a neighbouring hue that
stands out next to it (see color.py). Both settings are read through the freedesktop settings
portal, the same source Granite.Settings reads.
"""

from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from gi.repository import Gdk, Gio, GLib, Gtk

from .color import accent_pair

PORTAL_NAMESPACE = "org.freedesktop.appearance"
COLOR_SCHEME_KEY = "color-scheme"
ACCENT_KEY = "accent-color"
PREFER_DARK = 1  # 0 = no preference, 1 = prefer dark, 2 = prefer light
PRIORITY = Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
# elementary's Blueberry 500, for when the OS sets no accent
DEFAULT_ACCENT = (0x36 / 255, 0x89 / 255, 0xE6 / 255)


def _css_rgb(rgb: tuple[float, float, float]) -> str:
    r, g, b = (round(c * 255) for c in rgb)
    return f"rgb({r}, {g}, {b})"


def _provider(path: Path) -> Gtk.CssProvider:
    css = Gtk.CssProvider()
    css.load_from_path(str(path))
    return css


class Theme:
    def __init__(
        self, display: Gdk.Display, stylesheets: Iterable[Path], light_palette: Path, dark_palette: Path
    ) -> None:
        self._display = display
        for path in (light_palette, *stylesheets):
            Gtk.StyleContext.add_provider_for_display(display, _provider(path), PRIORITY)
        self._dark_palette = _provider(dark_palette)
        self._dark = False
        self._accent_rgb = DEFAULT_ACCENT
        self._accent = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_display(display, self._accent, PRIORITY + 2)
        self._color_scheme = AppearanceWatcher(COLOR_SCHEME_KEY, 0, lambda value: self._set_dark(value == PREFER_DARK))
        self._accent_color = AppearanceWatcher(ACCENT_KEY, (-1.0, -1.0, -1.0), self._set_accent)

    def _set_dark(self, dark: bool) -> None:
        # The theme's dark variant supplies @warning_color and @error_color;
        # the dark palette handles the rest.
        settings = Gtk.Settings.get_default()
        assert settings
        settings.props.gtk_application_prefer_dark_theme = dark
        if dark:
            Gtk.StyleContext.add_provider_for_display(self._display, self._dark_palette, PRIORITY + 1)
        else:
            Gtk.StyleContext.remove_provider_for_display(self._display, self._dark_palette)
        self._dark = dark
        self._load_accent()

    def _set_accent(self, rgb: tuple[float, float, float]) -> None:
        # Components outside 0..1 mean no accent is set.
        self._accent_rgb = rgb if all(0 <= c <= 1 for c in rgb) else DEFAULT_ACCENT
        self._load_accent()

    def _load_accent(self) -> None:
        pair = accent_pair(self._accent_rgb, self._dark)
        self._accent.load_from_string(
            f"@define-color ew_accent {_css_rgb(self._accent_rgb)};\n@define-color ew_accent_pair {_css_rgb(pair)};"
        )


class AppearanceWatcher:
    """Calls on_change(value) once with a portal appearance setting, then on every change."""

    def __init__(self, key: str, default: Any, on_change: Callable[[Any], None]) -> None:
        self._key = key
        self._on_change = on_change
        self._value: Any = object()
        try:
            self._proxy = Gio.DBusProxy.new_for_bus_sync(
                Gio.BusType.SESSION,
                Gio.DBusProxyFlags.DO_NOT_LOAD_PROPERTIES,
                None,
                "org.freedesktop.portal.Desktop",
                "/org/freedesktop/portal/desktop",
                "org.freedesktop.portal.Settings",
                None,
            )
            self._proxy.connect("g-signal", self._on_signal)
            value = self._proxy.call_sync(
                "ReadOne", GLib.Variant("(ss)", (PORTAL_NAMESPACE, key)), Gio.DBusCallFlags.NONE, -1, None
            ).unpack()[0]
        except GLib.Error:
            value = default  # no portal, or it lacks this setting
        self._update(value)

    def _on_signal(self, _proxy: Gio.DBusProxy, _sender: str | None, signal: str, params: GLib.Variant) -> None:
        if signal != "SettingChanged":
            return
        namespace, key, value = params.unpack()
        if (namespace, key) == (PORTAL_NAMESPACE, self._key):
            self._update(value)

    def _update(self, value: Any) -> None:
        if value != self._value:
            self._value = value
            self._on_change(value)
