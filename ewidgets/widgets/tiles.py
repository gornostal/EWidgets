"""Square one-tap tiles: Do Not Disturb, dark mode and lock screen.

The toggles use the same settings as the wingpanel's quick settings, so the
two stay in sync both ways.
"""

from gi.repository import Gio, GLib, Gtk

from ..core.blade import WidgetBlade

ICON_SIZE = 24

NOTIFICATIONS_SCHEMA = "io.elementary.notifications"
COLOR_SCHEME_SCHEMA = "io.elementary.settings-daemon.prefers-color-scheme"


def _settings(schema: str) -> Gio.Settings | None:
    """The Gio.Settings for `schema`, or None if it isn't installed."""
    source = Gio.SettingsSchemaSource.get_default()
    if source and source.lookup(schema, True):
        return Gio.Settings(schema_id=schema)
    return None


def _make_tile(button: Gtk.Button, icon: str, tooltip: str) -> None:
    """Turns `button` into a tile with an icon. A pressed toggle gets the accent fill.
    Whoever places the tile gives it its size."""
    button.set_icon_name(icon)
    button.set_tooltip_text(tooltip)
    button.add_css_class("tile")
    image = button.get_child()
    assert isinstance(image, Gtk.Image)
    image.set_pixel_size(ICON_SIZE)


class _Toggle(Gtk.ToggleButton):
    def __init__(self, icon: str, tooltip: str) -> None:
        super().__init__()
        _make_tile(self, icon, tooltip)


class DoNotDisturb(_Toggle):
    def __init__(self) -> None:
        super().__init__("notification-disabled-symbolic", "Do Not Disturb")
        self._settings = _settings(NOTIFICATIONS_SCHEMA)
        if self._settings:
            self._settings.bind("do-not-disturb", self, "active", Gio.SettingsBindFlags.DEFAULT)
        else:
            self.set_sensitive(False)


class DarkMode(_Toggle):
    def __init__(self) -> None:
        super().__init__("weather-clear-night-symbolic", "Dark Mode")
        settings = _settings(COLOR_SCHEME_SCHEMA)
        if not settings:
            self.set_sensitive(False)
            return
        self._settings = settings
        settings.connect("changed::color-scheme", lambda *_: self._sync())
        self._sync()
        self.connect("toggled", self._on_toggled)

    def _sync(self) -> None:
        self.set_active(self._settings.get_string("color-scheme") == "prefer-dark")

    def _on_toggled(self, _button: Gtk.ToggleButton) -> None:
        scheme = "prefer-dark" if self.get_active() else "no-preference"
        if self._settings.get_string("color-scheme") != scheme:
            self._settings.set_string("color-scheme", scheme)


class LockScreen(Gtk.Button):
    """Locks the session through Gala's org.gnome.ScreenSaver, like the quick settings' lock button."""

    def __init__(self) -> None:
        super().__init__()
        _make_tile(self, "system-lock-screen-symbolic", "Lock")
        self.connect("clicked", self._on_clicked)

    def _on_clicked(self, _button: Gtk.Button) -> None:
        blade = self.get_root()
        if isinstance(blade, WidgetBlade):
            blade.conceal()
        Gio.bus_get_sync(Gio.BusType.SESSION).call(
            "org.gnome.ScreenSaver",
            "/org/gnome/ScreenSaver",
            "org.gnome.ScreenSaver",
            "Lock",
            None,
            None,
            Gio.DBusCallFlags.NONE,
            -1,
            None,
            self._on_locked,
        )

    @staticmethod
    def _on_locked(bus: Gio.DBusConnection, result: Gio.AsyncResult) -> None:
        try:
            bus.call_finish(result)
        except GLib.Error as e:
            print(f"Unable to lock: {e.message}")
