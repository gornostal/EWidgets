"""Cards showing how much of their plan limits Claude Code and Codex have used:
a bar per limit (the 5-hour session, the week) with when it resets. A
per-model weekly limit shares the weekly bar, in its own colour.

Requests run on a worker thread, and the last usage is cached so the card has
something to show as soon as the blade opens.
"""

import threading
import time
from collections.abc import Callable

from gi.repository import GLib, Gtk

from .sources import Limit, SignInNeeded, Usage, fetch_claude, fetch_codex, load_cache, save_cache

# Often enough to follow a session, rarely enough not to be rate-limited.
REFRESH_INTERVAL_S = 5 * 60
BAR_WIDTH = 220
WARN_PERCENT = 75
HIGH_PERCENT = 90


def _resets(at: float | None) -> str:
    if at is None:
        return ""
    left = at - time.time()
    if left < 60:
        return "now"
    hours, minutes = divmod(round(left / 60), 60)
    if hours < 1:
        return f"in {minutes}m"
    if hours < 24:
        return f"in {hours}h {minutes}m"
    return time.strftime("%a %H:%M", time.localtime(at))


class _Meter(Gtk.Box):
    """One limit: its name, when it resets, and a bar. Limits of the same name
    and window (the whole week, and a single model's week) share the bar:
    their fills overlap, each in its own colour, named in a legend."""

    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        line = Gtk.Box(spacing=6)
        self._name = Gtk.Label(xalign=0, css_classes=["usage-name"])
        self._legend = Gtk.Box(spacing=5, hexpand=True)
        self._reset = Gtk.Label(xalign=1, css_classes=["usage-reset", "numeric"])
        for child in (self._name, self._legend, self._reset):
            line.append(child)
        self._stack = Gtk.Overlay()
        self._stack.set_size_request(BAR_WIDTH, -1)
        self.append(line)
        self.append(self._stack)
        self._labels: list[Gtk.Label] = []  # the legend's
        self._bars: list[Gtk.ProgressBar] = []  # bottom to top

    def _build(self, series: int) -> None:
        """Makes a bar per series, and a legend entry per series when there are several."""
        for bar in self._bars[1:]:
            self._stack.remove_overlay(bar)
        # The bottom bar draws the trough; the ones laid over it only their fill.
        self._bars = [Gtk.ProgressBar(css_classes=["usage-bar"])]
        self._bars += [Gtk.ProgressBar(css_classes=["usage-bar", "overlay"]) for _ in range(1, series)]
        self._stack.set_child(self._bars[0])
        for bar in self._bars[1:]:
            self._stack.add_overlay(bar)

        while child := self._legend.get_first_child():
            self._legend.remove(child)
        self._labels = []
        if series > 1:
            for index in range(series):
                self._labels.append(Gtk.Label(xalign=0, css_classes=["usage-name"]))
                self._legend.append(self._labels[-1])
                self._legend.append(Gtk.Box(valign=Gtk.Align.CENTER, css_classes=["usage-dot", f"series-{index}"]))

    def set(self, name: str, limits: list[Limit]) -> None:
        if len(limits) != len(self._bars):
            self._build(len(limits))
        self._name.set_label(f"{name}:" if len(limits) > 1 else name)
        self._reset.set_label(_resets(limits[0].resets_at))
        for label, limit in zip(self._labels, limits, strict=False):
            label.set_label(limit.model or "all")

        # Longest at the bottom, so each shorter fill is drawn over the longer ones.
        order = sorted(range(len(limits)), key=lambda i: -limits[i].percent)
        for bar, index in zip(self._bars, order, strict=True):
            percent = limits[index].percent
            bar.set_fraction(min(max(percent / 100, 0), 1))
            for series in range(len(limits)):
                if series == index:
                    bar.add_css_class(f"series-{series}")
                else:
                    bar.remove_css_class(f"series-{series}")
            # A lone bar warns as it nears its limit. Shared ones keep their legend colours.
            for level, threshold in (("warn", WARN_PERCENT), ("high", HIGH_PERCENT)):
                if len(limits) == 1 and percent >= threshold:
                    bar.add_css_class(level)
                else:
                    bar.remove_css_class(level)


class _UsageCard(Gtk.Box):
    def __init__(self, title: str, name: str, fetch: Callable[[], Usage]) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6, css_classes=["ai-usage"])
        self._name = name
        self._fetch = fetch
        self._usage = load_cache(name)
        self._problem: str | None = None  # why the last refresh failed
        self._fetching = False
        self._timer = 0

        header = Gtk.Box(spacing=6)
        header.append(Gtk.Label(label=title, xalign=0, hexpand=True, css_classes=["usage-title"]))
        # Heads the column of reset times below it.
        self._resets = Gtk.Label(label="Resets ↓", xalign=1, css_classes=["usage-reset"])
        header.append(self._resets)
        self.append(header)

        self._meters = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.append(self._meters)
        self._status = Gtk.Label(xalign=0, css_classes=["usage-status"])
        self.append(self._status)

        self.connect("map", self._on_map)
        self.connect("unmap", self._on_unmap)
        self._render()

    # Refreshing

    def _on_map(self, _widget: Gtk.Widget) -> None:
        self._render()  # counts the reset times down, even from the cache
        fetched_at = self._usage.fetched_at if self._usage else 0
        if time.time() - fetched_at >= REFRESH_INTERVAL_S:
            self._refresh()
        self._timer = GLib.timeout_add_seconds(REFRESH_INTERVAL_S, self._refresh)

    def _on_unmap(self, _widget: Gtk.Widget) -> None:
        if self._timer:
            GLib.source_remove(self._timer)
            self._timer = 0

    def _refresh(self) -> bool:
        if not self._fetching:
            self._fetching = True
            threading.Thread(target=self._fetch_in_background, daemon=True).start()
        return GLib.SOURCE_CONTINUE

    def _fetch_in_background(self) -> None:
        usage, problem = None, None
        try:
            usage = self._fetch()
        except SignInNeeded as e:
            problem = str(e)
        except Exception as e:  # noqa: BLE001 - any failure just keeps the old usage
            print(f"ewidgets: {self._name} usage update failed: {e}")
            problem = "Usage unavailable"
        else:
            save_cache(self._name, usage)
        GLib.idle_add(self._on_fetched, usage, problem)

    def _on_fetched(self, usage: Usage | None, problem: str | None) -> bool:
        self._fetching = False
        self._problem = problem
        if usage:
            self._usage = usage
        self._render()
        return GLib.SOURCE_REMOVE

    # Drawing

    def _render(self) -> None:
        usage = self._usage
        # Limits of the same name share a meter.
        limits: dict[str, list[Limit]] = {}
        for limit in usage.limits if usage else []:
            limits.setdefault(limit.name, []).append(limit)

        meters = []
        child = self._meters.get_first_child()
        while child:
            meters.append(child)
            child = child.get_next_sibling()
        for meter in meters[len(limits) :]:
            self._meters.remove(meter)
        for _ in range(len(meters), len(limits)):
            self._meters.append(_Meter())
        child = self._meters.get_first_child()
        for name, group in limits.items():
            assert isinstance(child, _Meter)
            child.set(name, group)
            child = child.get_next_sibling()
        self._meters.set_visible(bool(limits))
        self._resets.set_visible(bool(limits))

        if self._problem:
            status = self._problem
        elif not usage:
            status = "Loading…"
        else:
            status = ""
        self._status.set_label(status)
        self._status.set_visible(bool(status))
        if usage:
            updated = time.strftime("Updated %H:%M", time.localtime(usage.fetched_at))
            self.set_tooltip_text(f"{usage.plan} plan · {updated}" if usage.plan else updated)


class ClaudeUsage(_UsageCard):
    def __init__(self) -> None:
        super().__init__("Claude", "claude", fetch_claude)


class CodexUsage(_UsageCard):
    def __init__(self) -> None:
        super().__init__("Codex", "codex", fetch_codex)
