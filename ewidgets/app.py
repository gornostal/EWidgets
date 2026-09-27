import os
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, Gio, Gtk  # noqa: E402

from . import APP_ID  # noqa: E402
from .core.theme import Theme  # noqa: E402

if TYPE_CHECKING:
    from .core.blade import WidgetBlade

STYLES = Path(__file__).with_name("styles")
COMMANDS = ("daemon", "show", "hide", "toggle", "quit")
USAGE = f"usage: python3 -m ewidgets [{'|'.join(COMMANDS)}]"


class EWidgetsApp(Gtk.Application):
    """Single-instance app. Later invocations forward their command to the running one."""

    blade: "WidgetBlade"

    def __init__(self) -> None:
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        handlers: tuple[tuple[str, Callable[[], object]], ...] = (
            ("show", lambda: self.blade.reveal()),
            ("hide", lambda: self.blade.conceal()),
            ("toggle", lambda: self.blade.toggle()),
            ("quit", self.quit),
        )
        for name, handler in handlers:
            action = Gio.SimpleAction(name=name)
            action.connect("activate", lambda _a, _p, h=handler: h())
            self.add_action(action)

    def do_startup(self) -> None:
        Gtk.Application.do_startup(self)
        if "WAYLAND_DISPLAY" not in os.environ:
            raise SystemExit("EWidgets needs a Wayland session running Gala (Pantheon).")

        display = Gdk.Display.get_default()
        assert display
        self._theme = Theme(
            display, sorted(STYLES.glob("*.css")), STYLES / "palette" / "light.css", STYLES / "palette" / "dark.css"
        )

        from .core.blade import WidgetBlade
        from .widgets.ai_usage import ClaudeUsage, CodexUsage
        from .widgets.countdown import Countdown
        from .widgets.media_player import MediaPlayer
        from .widgets.tiles import DarkMode, DoNotDisturb, LockScreen
        from .widgets.weather import Weather

        cards: list[Gtk.Widget] = [Weather(), MediaPlayer()]
        tiles: list[Gtk.Widget] = [DoNotDisturb(), DarkMode(), LockScreen()]
        usage: list[Gtk.Widget] = [ClaudeUsage(), CodexUsage()]
        self.blade = WidgetBlade(self, [[cards], [tiles, usage, [Countdown()]]])
        # Tiles are at least as wide as the cards above them are tall, and
        # widen to fill the row. They stretch to the height of the usage cards
        # beside them. Measured once the blade has given the cards their style.
        size = max(card.measure(Gtk.Orientation.VERTICAL, -1)[1] for card in cards)
        for tile in tiles:
            tile.set_size_request(size, size)
            tile.set_hexpand(True)
        self.hold()  # keep running while the blade is hidden

    def do_command_line(self, command_line: Gio.ApplicationCommandLine) -> int:
        args = command_line.get_arguments()[1:]
        command = args[0] if args else "daemon"
        if command not in COMMANDS or len(args) > 1:
            command_line.printerr_literal(USAGE + "\n")
            return 2
        if command != "daemon":
            self.activate_action(command, None)
        return 0

    def do_activate(self) -> None:
        self.blade.reveal()
