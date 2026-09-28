"""What happens when a countdown runs out: a desktop notification and a sound.

The sound is alarm.wav, a glassy two-note ping.
"""

from pathlib import Path

from gi.repository import Gio, GLib, Gtk

from ... import APP_ID

SOUND = Path(__file__).with_name("alarm.wav")
NOTIFICATION_ICON = "alarm-symbolic"
NOTIFICATION_HINTS = {
    # The notification center keeps only notifications from an installed app
    # (install.sh writes its .desktop file); the rest vanish unseen.
    "desktop-entry": GLib.Variant("s", APP_ID),
    # Critical: the bubble stays on screen until it's dismissed.
    "urgency": GLib.Variant("y", 2),
}


class Alarm:
    def __init__(self) -> None:
        self._sound: Gtk.MediaFile | None = None  # kept alive while it plays
        self._notification_id = 0

    def ring(self, title: str, body: str) -> None:
        self._notify(title, body)
        self._sound = Gtk.MediaFile.new_for_filename(str(SOUND))
        self._sound.play()

    def _notify(self, title: str, body: str) -> None:
        # Through the notification server directly: Gio.Notification would
        # need a .desktop file for the app.
        Gio.bus_get_sync(Gio.BusType.SESSION).call(
            "org.freedesktop.Notifications",
            "/org/freedesktop/Notifications",
            "org.freedesktop.Notifications",
            "Notify",
            GLib.Variant(
                "(susssasa{sv}i)",
                ("EWidgets", self._notification_id, NOTIFICATION_ICON, title, body, [], NOTIFICATION_HINTS, -1),
            ),
            GLib.VariantType("(u)"),
            Gio.DBusCallFlags.NONE,
            -1,
            None,
            self._on_notified,
        )

    def _on_notified(self, bus: Gio.DBusConnection, result: Gio.AsyncResult) -> None:
        try:
            # Replaces the previous timer's notification rather than stacking up.
            (self._notification_id,) = bus.call_finish(result).unpack()
        except GLib.Error as e:
            print(f"Unable to show a notification: {e.message}")
