"""Animation helpers shared by the blade and anything else that slides:
an eased animation on a widget's frame clock, and the speed of a drag."""

from collections.abc import Callable

from gi.repository import Gdk, GLib, Gtk

VELOCITY_WINDOW_US = 100_000


def ease_out_cubic(t: float) -> float:
    return 1 - (1 - t) ** 3


class Tween:
    """Moves a value from `start` to `end`, calling on_step(value) on every frame
    of `widget`'s frame clock and on_done() once it arrives."""

    def __init__(self, widget: Gtk.Widget, on_step: Callable[[float], None]) -> None:
        self._widget = widget
        self._on_step = on_step
        self._on_done: Callable[[], None] | None = None
        self._tick = 0
        self._from = self._to = 0.0
        self._start = 0
        self._duration = 1.0

    def start(self, start: float, end: float, duration_us: float, on_done: Callable[[], None] | None = None) -> bool:
        """Returns False, without animating, if the widget has no frame clock yet."""
        self.stop()
        clock = self._widget.get_frame_clock()
        if not clock:
            return False
        self._from, self._to = start, end
        self._start = clock.get_frame_time()
        self._duration = max(duration_us, 1)
        self._on_done = on_done
        self._tick = self._widget.add_tick_callback(self._on_tick)
        return True

    @property
    def running(self) -> bool:
        return bool(self._tick)

    def stop(self) -> None:
        if self._tick:
            self._widget.remove_tick_callback(self._tick)
            self._tick = 0

    def _on_tick(self, _widget: Gtk.Widget, clock: Gdk.FrameClock) -> bool:
        t = min((clock.get_frame_time() - self._start) / self._duration, 1.0)
        self._on_step(self._from + (self._to - self._from) * ease_out_cubic(t))
        if t < 1.0:
            return GLib.SOURCE_CONTINUE
        self._tick = 0
        if self._on_done:
            self._on_done()
        return GLib.SOURCE_REMOVE


class VelocityTracker:
    """How fast a dragged value moved over its last VELOCITY_WINDOW_US, per second."""

    def __init__(self) -> None:
        self._samples: list[tuple[int, float]] = []  # (time, value)

    @property
    def empty(self) -> bool:
        return not self._samples

    def reset(self) -> None:
        self._samples = []

    def add(self, value: float) -> None:
        now = GLib.get_monotonic_time()
        self._samples.append((now, value))
        self._samples = [s for s in self._samples if now - s[0] <= VELOCITY_WINDOW_US]

    def velocity(self) -> float:
        if not self._samples:
            return 0
        (t0, v0), (t1, v1) = self._samples[0], self._samples[-1]
        return (v1 - v0) / (t1 - t0) * 1_000_000 if t1 > t0 else 0
