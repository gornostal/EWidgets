"""Live touchpad swipes from the Touchégg daemon.

`touchegg --daemon` broadcasts every gesture over a private D-Bus socket as
begin / update / end signals with a 0-100 completion percentage, so the blade
can follow the fingers instead of reacting once the gesture is recognised.
The percentage falls again if the fingers move back.
Protocol: https://github.com/JoseExposito/touchegg/blob/master/src/daemon/dbus.h
"""

from collections.abc import Callable

from gi.repository import Gio, GLib

ADDRESS = "unix:abstract=touchegg"
OBJECT_PATH = "/io/github/joseexposito/Touchegg"
INTERFACE = "io.github.joseexposito.Touchegg"

SWIPE = 1
UP, DOWN = 1, 2
TOUCHPAD = 1

RECONNECT_DELAY_S = 5


class SwipeListener:
    """Calls on_begin(direction), on_update(direction, fraction) and
    on_end(direction, fraction) for vertical swipes with `fingers` fingers."""

    def __init__(
        self,
        fingers: int,
        on_begin: Callable[[int], None],
        on_update: Callable[[int, float], None],
        on_end: Callable[[int, float], None],
    ) -> None:
        self._fingers = fingers
        self._handlers: dict[str, Callable[..., None]] = {
            "OnGestureBegin": on_begin,
            "OnGestureUpdate": on_update,
            "OnGestureEnd": on_end,
        }
        self._connection: Gio.DBusConnection | None = None
        self._connect()

    def _connect(self) -> None:
        Gio.DBusConnection.new_for_address(
            ADDRESS, Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT, None, None, self._on_connected
        )

    def _on_connected(self, _source: object, result: Gio.AsyncResult) -> None:
        try:
            self._connection = connection = Gio.DBusConnection.new_for_address_finish(result)
        except GLib.Error as e:
            print(f"ewidgets: can't reach the Touchégg daemon ({e.message}); retrying")
            self._retry()
            return
        connection.signal_subscribe(None, INTERFACE, None, OBJECT_PATH, None, Gio.DBusSignalFlags.NONE, self._on_signal)
        connection.connect("closed", lambda *_: self._retry())

    def _retry(self) -> None:
        self._connection = None
        GLib.timeout_add_seconds(RECONNECT_DELAY_S, lambda: self._connect() or GLib.SOURCE_REMOVE)

    def _on_signal(
        self, _conn: Gio.DBusConnection, _sender: str | None, _path: str, _iface: str, name: str, params: GLib.Variant
    ) -> None:
        handler = self._handlers.get(name)
        gesture, direction, percentage, fingers, device, _elapsed = params.unpack()
        if handler and gesture == SWIPE and direction in (UP, DOWN) and fingers == self._fingers and device == TOUCHPAD:
            if name == "OnGestureBegin":
                handler(direction)
            else:
                handler(direction, percentage / 100)
