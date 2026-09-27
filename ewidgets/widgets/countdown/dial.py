"""A scrollable number wheel, like an iOS picker: the numbers sit on a drum
that turns under a drag, a touchpad scroll or the mouse wheel, then settles on
the number in the middle. It wraps around, so after 59 comes 0 again.

The numbers are drawn straight from snapshot with Pango. Each one is placed
on the drum by its angle, flattened and faded as it turns away.
"""

import math
from collections.abc import Callable

from gi.repository import Gdk, Graphene, Gtk

from ...core.motion import Tween, VelocityTracker

ROW_HEIGHT = 28
ROW_ANGLE = 0.4  # radians of drum per number
RADIUS = ROW_HEIGHT / ROW_ANGLE
WIDTH = 44
SETTLE_DURATION_US = 250_000
MAX_SETTLE_DURATION_US = 700_000
# On release, how far the drum keeps turning, in seconds of its speed.
FLING_TIME_S = 0.25
# A press that moves less than this (px) is a click on a number.
CLICK_SLOP = 4


class Dial(Gtk.Widget):
    """Picks a number from 0 to count - 1. `on_changed(value)` runs whenever
    the number in the middle changes, including mid-turn."""

    def __init__(self, count: int, tooltip: str, on_changed: Callable[[int], None] | None = None) -> None:
        super().__init__(
            focusable=True, vexpand=True, overflow=Gtk.Overflow.HIDDEN, tooltip_text=tooltip, css_classes=["dial"]
        )
        self._count = count
        self._position = 0.0  # the number in the middle; fractional mid-turn, unbounded
        self._target = 0.0  # where the drum is settling
        self._value = 0
        self._on_changed = on_changed
        self._tween = Tween(self, self._set_position)
        self._velocity = VelocityTracker()
        self._drag_start = 0.0

        drag = Gtk.GestureDrag()
        drag.connect("drag-begin", self._on_drag_begin)
        drag.connect("drag-update", self._on_drag_update)
        drag.connect("drag-end", self._on_drag_end)
        self.add_controller(drag)

        scroll = Gtk.EventControllerScroll(flags=Gtk.EventControllerScrollFlags.VERTICAL)
        scroll.connect("scroll-begin", lambda *_: self._begin_turn())
        scroll.connect("scroll", self._on_scroll)
        scroll.connect("scroll-end", lambda *_: self._fling())
        self.add_controller(scroll)

        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self._on_key_pressed)
        self.add_controller(keys)

    @property
    def value(self) -> int:
        return self._value

    def set_value(self, value: int, animate: bool = True) -> None:
        self.turn_to(self._position + self._shortest(value % self._count - self._value), animate)

    def turn_to(self, position: float, animate: bool = True) -> None:
        """Turns the drum until `position` (a whole number) is in the middle."""
        self._tween.stop()
        self._target = position
        distance = abs(position - self._position)
        duration = min(SETTLE_DURATION_US * max(math.sqrt(distance), 1), MAX_SETTLE_DURATION_US)
        if not (animate and distance and self.get_mapped() and self._tween.start(self._position, position, duration)):
            self._set_position(position)

    def _shortest(self, steps: int) -> int:
        """`steps` or the equivalent turn the other way round, whichever is shorter."""
        steps %= self._count
        return steps - self._count if steps > self._count / 2 else steps

    def _set_position(self, position: float) -> None:
        self._position = position
        self.queue_draw()
        value = round(position) % self._count
        if value != self._value:
            self._value = value
            if self._on_changed:
                self._on_changed(value)

    # Drawing

    def do_measure(self, orientation: Gtk.Orientation, for_size: int) -> tuple[int, int, int, int]:
        if orientation == Gtk.Orientation.HORIZONTAL:
            return WIDTH, WIDTH, -1, -1
        return 3 * ROW_HEIGHT, 3 * ROW_HEIGHT, -1, -1

    def do_snapshot(self, snapshot: Gtk.Snapshot) -> None:
        width, height = self.get_width(), self.get_height()
        color = self.get_color()
        # Only the numbers facing us, and only as many as fit.
        reach = min(math.pi / 2, math.asin(min(height / 2 / RADIUS, 1)) + ROW_ANGLE / 2)
        first = math.ceil(self._position - reach / ROW_ANGLE)
        last = math.floor(self._position + reach / ROW_ANGLE)
        for index in range(first, last + 1):
            angle = (index - self._position) * ROW_ANGLE
            if abs(angle) >= math.pi / 2:
                continue
            squash = math.cos(angle)
            layout = self.create_pango_layout(f"{index % self._count:02}")
            _ink, logical = layout.get_pixel_extents()
            faded = Gdk.RGBA()
            faded.red, faded.green, faded.blue = color.red, color.green, color.blue
            faded.alpha = color.alpha * squash**6
            snapshot.save()
            snapshot.translate(Graphene.Point().init(width / 2, height / 2 + RADIUS * math.sin(angle)))
            snapshot.scale(1, squash)
            snapshot.translate(Graphene.Point().init(-logical.width / 2, -logical.height / 2))
            snapshot.append_layout(layout, faded)
            snapshot.restore()

    # Turning

    def _begin_turn(self) -> None:
        self._tween.stop()
        self._velocity.reset()

    def _turn_by(self, rows: float) -> None:
        self._set_position(self._position + rows)
        self._velocity.add(self._position)

    def _fling(self) -> None:
        """Lets the drum coast on at its release speed, then settle on a number."""
        velocity = self._velocity.velocity()
        self._velocity.reset()
        self.turn_to(round(self._position + velocity * FLING_TIME_S))

    def _on_drag_begin(self, _gesture: Gtk.GestureDrag, _x: float, _y: float) -> None:
        self._begin_turn()
        self._drag_start = self._position
        self.grab_focus()

    def _on_drag_update(self, _gesture: Gtk.GestureDrag, _dx: float, dy: float) -> None:
        # Dragging up brings up the numbers below.
        self._set_position(self._drag_start - dy / ROW_HEIGHT)
        self._velocity.add(self._position)

    def _on_drag_end(self, gesture: Gtk.GestureDrag, dx: float, dy: float) -> None:
        if math.hypot(dx, dy) >= CLICK_SLOP:
            self._fling()
            return
        # A click on a number above or below the middle turns it into place.
        _ok, _x, y = gesture.get_start_point()
        offset = (y - self.get_height() / 2) / RADIUS
        rows = math.asin(min(max(offset, -1), 1)) / ROW_ANGLE
        self.turn_to(round(self._drag_start + rows))

    def _on_scroll(self, ctrl: Gtk.EventControllerScroll, _dx: float, dy: float) -> bool:
        if not dy:
            return False
        if ctrl.get_unit() == Gdk.ScrollUnit.WHEEL:
            step = 1 if dy > 0 else -1
            self.turn_to(round(self._settling_at()) + step)
        else:
            self._tween.stop()
            self._turn_by(dy / ROW_HEIGHT)
        return True

    def _settling_at(self) -> float:
        # Wheel notches and key presses pile up while the drum is still turning.
        return self._target if self._tween.running else self._position

    def _on_key_pressed(self, _ctrl: Gtk.EventControllerKey, keyval: int, _code: int, _state: Gdk.ModifierType) -> bool:
        steps = {Gdk.KEY_Up: -1, Gdk.KEY_Down: 1, Gdk.KEY_Page_Up: -5, Gdk.KEY_Page_Down: 5}.get(keyval)
        if steps is None:
            return False
        self.turn_to(round(self._settling_at()) + steps)
        return True
