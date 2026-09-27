"""The countdown card: hours and minutes dials, then start / pause and stop.

While it runs, the dials give way to the time left. The countdown goes on
while the blade is hidden, and keeps to the wall clock, so it also ends on
time after a suspend.
"""

import math
from datetime import datetime, timedelta
from enum import Enum, auto

from gi.repository import GLib, Gtk

from .alarm import Alarm
from .dial import ROW_HEIGHT, Dial

TICK_MS = 200
US_PER_S = 1_000_000


class _State(Enum):
    SETTING = auto()
    RUNNING = auto()
    PAUSED = auto()


def _clock(seconds: int) -> str:
    hours, rest = divmod(seconds, 3600)
    minutes, seconds = divmod(rest, 60)
    return f"{hours}:{minutes:02}:{seconds:02}" if hours else f"{minutes}:{seconds:02}"


def _duration(seconds: int) -> str:
    hours, minutes = divmod(seconds // 60, 60)
    parts = ([f"{hours} h"] if hours else []) + ([f"{minutes} min"] if minutes else [])
    return " ".join(parts)


class Countdown(Gtk.Box):
    def __init__(self) -> None:
        super().__init__(spacing=14, css_classes=["countdown"])
        self._state = _State.SETTING
        self._total_us = 0
        self._left_us = 0  # while paused
        self._deadline_us = 0  # while running, in GLib.get_real_time()
        self._tick = 0
        self._alarm = Alarm()

        self._hours = Dial(24, "Hours", lambda _: self._sync())
        self._minutes = Dial(60, "Minutes", lambda _: self._sync())
        self._stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE, hexpand=True)
        self._stack.add_named(self._build_picker(), "picker")
        self._stack.add_named(self._build_progress(), "progress")
        self.append(self._stack)

        controls = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, valign=Gtk.Align.CENTER)
        self._start = Gtk.Button(css_classes=["countdown-start"])
        self._start.connect("clicked", self._on_start_clicked)
        self._stop = Gtk.Button(icon_name="media-playback-stop-symbolic", tooltip_text="Stop", halign=Gtk.Align.CENTER)
        self._stop.connect("clicked", lambda *_: self._reset())
        controls.append(self._start)
        controls.append(self._stop)
        self.append(controls)

        self._minutes.set_value(5, animate=False)
        self._sync()

    def _build_picker(self) -> Gtk.Widget:
        # The band marks the middle row, behind the dials' numbers.
        band = Gtk.Box(valign=Gtk.Align.CENTER, css_classes=["dial-band"])
        band.set_size_request(-1, ROW_HEIGHT)
        dials = Gtk.Box(spacing=2, halign=Gtk.Align.CENTER)
        for dial, unit in ((self._hours, "h"), (self._minutes, "min")):
            dials.append(dial)
            dials.append(Gtk.Label(label=unit, valign=Gtk.Align.CENTER, xalign=0, css_classes=["dial-unit"]))
        picker = Gtk.Overlay(child=band)
        picker.add_overlay(dials)
        picker.set_measure_overlay(dials, True)
        return picker

    def _build_progress(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, valign=Gtk.Align.CENTER)
        self._time = Gtk.Label(css_classes=["countdown-time", "numeric"])
        self._caption = Gtk.Label(css_classes=["countdown-caption"])
        self._bar = Gtk.ProgressBar(css_classes=["countdown-bar"])
        for child in (self._time, self._caption, self._bar):
            box.append(child)
        return box

    @property
    def _set_us(self) -> int:
        """The time on the dials."""
        return (self._hours.value * 3600 + self._minutes.value * 60) * US_PER_S

    # State

    def _on_start_clicked(self, _button: Gtk.Button) -> None:
        if self._state == _State.RUNNING:
            self._left_us = self._deadline_us - GLib.get_real_time()
            self._state = _State.PAUSED
        else:
            if self._state == _State.SETTING:
                self._total_us = self._left_us = self._set_us
            self._deadline_us = GLib.get_real_time() + self._left_us
            self._state = _State.RUNNING
        self._sync()

    def _reset(self) -> None:
        self._state = _State.SETTING
        self._sync()

    def _on_tick(self) -> bool:
        if GLib.get_real_time() < self._deadline_us:
            self._show_time_left()
            return GLib.SOURCE_CONTINUE
        self._tick = 0
        self._state = _State.SETTING
        self._sync()
        self._alarm.ring("Time is up", f"Your {_duration(self._total_us // US_PER_S)} countdown has finished.")
        return GLib.SOURCE_REMOVE

    # UI

    def _sync(self) -> None:
        running = self._state == _State.RUNNING
        if running and not self._tick:
            self._tick = GLib.timeout_add(TICK_MS, self._on_tick)
        elif not running and self._tick:
            GLib.source_remove(self._tick)
            self._tick = 0

        setting = self._state == _State.SETTING
        self._stack.set_visible_child_name("picker" if setting else "progress")
        self._start.set_icon_name("media-playback-pause-symbolic" if running else "media-playback-start-symbolic")
        self._start.set_tooltip_text("Pause" if running else "Start")
        self._start.set_sensitive(not setting or self._set_us > 0)
        self._stop.set_sensitive(not setting)
        if not setting:
            self._show_time_left()

    def _show_time_left(self) -> None:
        running = self._state == _State.RUNNING
        left_us = self._deadline_us - GLib.get_real_time() if running else self._left_us
        self._time.set_label(_clock(math.ceil(max(left_us, 0) / US_PER_S)))
        if running:
            end = datetime.now() + timedelta(microseconds=left_us)
            self._caption.set_label(f"Ends at {end:%H:%M}")
            self._time.remove_css_class("paused")
        else:
            self._caption.set_label("Paused")
            self._time.add_css_class("paused")
        self._bar.set_fraction(left_us / self._total_us if self._total_us else 0)
