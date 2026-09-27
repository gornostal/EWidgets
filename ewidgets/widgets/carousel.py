"""Pages side by side, one in view at a time, with dots to show where you are.

A two-finger horizontal swipe on the touchpad drags the pages along with the
fingers, then settles on a page when they lift. A horizontal mouse wheel or a
click on a dot moves one page.
"""

import math
from collections.abc import Callable

from gi.repository import Gdk, Graphene, Gsk, Gtk

from ..core.motion import Tween, VelocityTracker

SLIDE_DURATION_US = 250_000
# On release, a swipe faster than this (pages per second) moves on to the
# next page in its direction. A slower one settles on the nearest page.
FLICK_VELOCITY = 1.5


class Carousel(Gtk.Widget):
    def __init__(self, on_page_changed: Callable[[int], None] | None = None) -> None:
        super().__init__(overflow=Gtk.Overflow.HIDDEN, hexpand=True, vexpand=True)
        self._pages: list[Gtk.Widget] = []
        self._position = 0.0  # 0 = first page in view, 1 = second, ...
        self._on_page_changed = on_page_changed
        self._page = 0
        self._velocity = VelocityTracker()
        self._tween = Tween(self, self._set_position)

        scroll = Gtk.EventControllerScroll(flags=Gtk.EventControllerScrollFlags.HORIZONTAL)
        scroll.connect("scroll-begin", self._on_scroll_begin)
        scroll.connect("scroll", self._on_scroll)
        scroll.connect("scroll-end", self._on_scroll_end)
        self.add_controller(scroll)

    @property
    def n_pages(self) -> int:
        return len(self._pages)

    @property
    def page(self) -> int:
        return self._page

    def append(self, page: Gtk.Widget) -> None:
        page.set_parent(self)
        self._pages.append(page)
        self.queue_resize()

    def scroll_to(self, page: int) -> None:
        page = min(max(page, 0), self.n_pages - 1)
        self._tween.stop()
        if self.get_mapped() and page != self._position:
            duration = SLIDE_DURATION_US * min(abs(page - self._position), 1.0)
            if self._tween.start(self._position, page, duration):
                return
        self._set_position(page)

    # Layout: every page gets the carousel's full size, shifted into place.

    def do_measure(self, orientation: Gtk.Orientation, for_size: int) -> tuple[int, int, int, int]:
        minimum = natural = 0
        for page in self._pages:
            page_min, page_nat, _, _ = page.measure(orientation, for_size)
            minimum, natural = max(minimum, page_min), max(natural, page_nat)
        return minimum, natural, -1, -1

    def do_size_allocate(self, width: int, height: int, baseline: int) -> None:
        for i, page in enumerate(self._pages):
            shift = Gsk.Transform().translate(Graphene.Point().init(round((i - self._position) * width), 0))
            page.allocate(width, height, baseline, shift)

    def _set_position(self, position: float) -> None:
        self._position = position
        self.queue_allocate()
        page = round(position)
        if page != self._page:
            self._page = page
            if self._on_page_changed:
                self._on_page_changed(page)

    # Swipes

    def _on_scroll_begin(self, _ctrl: Gtk.EventControllerScroll) -> None:
        self._tween.stop()
        self._velocity.reset()

    def _on_scroll(self, ctrl: Gtk.EventControllerScroll, dx: float, _dy: float) -> bool:
        if not dx:
            return False
        if ctrl.get_unit() == Gdk.ScrollUnit.WHEEL:
            self.scroll_to(round(self._position) + (1 if dx > 0 else -1))
            return True
        width = self.get_width()
        if not width:
            return False
        self._tween.stop()
        position = min(max(self._position + dx / width, 0.0), self.n_pages - 1.0)
        self._velocity.add(position)
        self._set_position(position)
        return True

    def _on_scroll_end(self, _ctrl: Gtk.EventControllerScroll) -> None:
        if self._velocity.empty:
            return
        velocity = self._velocity.velocity()
        self._velocity.reset()
        if velocity > FLICK_VELOCITY:
            target = math.floor(self._position) + 1
        elif velocity < -FLICK_VELOCITY:
            target = math.ceil(self._position) - 1
        else:
            target = round(self._position)
        self.scroll_to(target)


class CarouselDots(Gtk.Box):
    """One dot per page; the current page's is filled in. Clicking a dot goes to its page."""

    def __init__(self, carousel: Carousel) -> None:
        super().__init__(spacing=2, halign=Gtk.Align.CENTER, css_classes=["carousel-dots"])
        self._dots: list[Gtk.Button] = []
        for i in range(carousel.n_pages):
            dot = Gtk.Button(tooltip_text=f"Page {i + 1}", css_classes=["carousel-dot"])
            dot.connect("clicked", lambda _b, i=i: carousel.scroll_to(i))
            self.append(dot)
            self._dots.append(dot)
        self.set_page(carousel.page)

    def set_page(self, page: int) -> None:
        for i, dot in enumerate(self._dots):
            if i == page:
                dot.add_css_class("active")
            else:
                dot.remove_css_class("active")
