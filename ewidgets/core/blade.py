"""The widget blade: a pantheon-shell panel that slides down from under the
wingpanel, following the fingers during a three-finger swipe.

Gala's own panel slide can't be scrubbed, so the blade does its own: it moves
its content inside the transparent surface. Gala still has to keep the panel
on screen, which with hide_mode=ALWAYS it does only while the panel is focused
or hovered. So a swipe down maps the window with the content out of sight and
asks Gala to focus it. Gala slides the (still empty) surface in within ~200 ms,
while the content follows the fingers. Once concealed, the window is unmapped:
that hands focus back to the previous window, and keeps Gala's top-edge reveal
barrier from popping the blade open when the pointer hits the wingpanel.

hide_mode=NEVER would avoid Gala's slide but hangs Gala 8.6 (the whole screen
stops repainting) as soon as the panel draws anything.
"""

from collections.abc import Sequence

import cairo
from gi.repository import Gdk, GLib, Graphene, Gsk, Gtk

from .. import config
from . import gestures
from . import pantheon_shell as ps
from .motion import Tween, VelocityTracker

# Keep in sync with .blade-content's border-radius in styles/blade.css.
CORNER_RADIUS = 18
# Where the glass glows, its edge takes the glass's colour there instead of
# the grey rim and hairline. Keep in sync with .blade-content's
# background-image: each glow's centre and radii as fractions of the blade's
# size, and its strength relative to @ew_glow (@ew_glow_soft is about 0.62 of it).
RIM_WIDTH = 1
HAIRLINE_WIDTH = 0.5  # the hairline box-shadow just outside the glass
RIM_GLOWS = ((0.12, 0.0, 0.28, 0.52, 1.0), (0.96, 1.0, 0.14, 0.32, 0.62))
CARD_SPACING = 10
# Gala places the panel right below the wingpanel. Like io.elementary.dock's
# 9px bottom-margin, a transparent strip keeps the glass just clear of it.
# The other margins leave room for the drop shadow.
MARGIN_TOP = 9
MARGIN_SIDE = 40
MARGIN_BOTTOM = 50
# A full slide, like Gala's panel slide. Shorter distances take proportionally less.
SLIDE_DURATION_US = 250_000
MIN_SLIDE_DURATION_US = 100_000
# 3 or 4, from [gesture] fingers= in ewidgets.conf, as set up by install.sh.
SWIPE_FINGERS = config.get_int("gesture", "fingers", 3)
# How far the blade moves per unit of Touchégg's swipe progress. Above 1, a
# shorter swipe reveals it fully.
SWIPE_SENSITIVITY = 1.6
# On release, a swipe faster than this (blade heights per second) finishes in
# its direction of travel. A slower one snaps to whichever end is closer.
FLICK_VELOCITY = 0.8


class _Slide(Gtk.Widget):
    """Lays out its child at full size, then shifts it up by `hidden` of its height."""

    def __init__(self, child: Gtk.Widget) -> None:
        super().__init__()
        self.hidden = 1.0
        self._child = child
        child.set_parent(self)

    def offset(self) -> int:
        return round(self.hidden * self.get_height())

    def set_hidden(self, hidden: float) -> None:
        self.hidden = hidden
        self.queue_allocate()

    def do_measure(self, orientation: Gtk.Orientation, for_size: int) -> tuple[int, int, int, int]:
        return self._child.measure(orientation, for_size)

    def do_size_allocate(self, width: int, height: int, baseline: int) -> None:
        shift = Gsk.Transform().translate(Graphene.Point().init(0, -round(self.hidden * height)))
        self._child.allocate(width, height, baseline, shift)


class _Rim(Gtk.Widget):
    """The glass's edge, in its CSS colour where the glass glows.

    Covers the rim and the hairline outside it, fading to nothing so the grey
    edge shows everywhere else."""

    def __init__(self) -> None:
        super().__init__(css_classes=["blade-rim"], can_target=False)

    def do_snapshot(self, snapshot: Gtk.Snapshot) -> None:
        width, height = self.get_width(), self.get_height()
        out = HAIRLINE_WIDTH
        bounds = Graphene.Rect().init(-out, -out, width + 2 * out, height + 2 * out)
        outline = Gsk.RoundedRect()
        outline.init_from_rect(bounds, CORNER_RADIUS + out)
        color = self.get_color()

        # The outline is the mask, the glows are what shows through it.
        snapshot.push_mask(Gsk.MaskMode.ALPHA)
        snapshot.append_border(outline, [RIM_WIDTH + out] * 4, [_with_alpha(color, 1)] * 4)
        snapshot.pop()
        for x, y, x_radius, y_radius, strength in RIM_GLOWS:
            lit = _with_alpha(color, color.alpha * strength)
            snapshot.append_radial_gradient(
                bounds,
                Graphene.Point().init(x * width, y * height),
                x_radius * width,
                y_radius * height,
                0,
                1,
                [_stop(0, lit), _stop(1, _with_alpha(color, 0))],
            )
        snapshot.pop()


def _with_alpha(color: Gdk.RGBA, alpha: float) -> Gdk.RGBA:
    copy = color.copy()
    copy.alpha = alpha
    return copy


def _stop(offset: float, color: Gdk.RGBA) -> Gsk.ColorStop:
    stop = Gsk.ColorStop()
    stop.offset = offset
    stop.color = color
    return stop


class WidgetBlade(Gtk.Window):
    """Shows `rows` of widgets on the blade's glass, each widget on its own
    .widget-card. A row is a sequence of groups; cards in a group share one
    width, their widest widget's, and are as tall as the row.
    Rows are as wide as the widest one. A narrower row gives the spare width
    to its widgets that set hexpand, or else leaves it empty on the right."""

    def __init__(self, app: Gtk.Application, rows: Sequence[Sequence[Sequence[Gtk.Widget]]]) -> None:
        super().__init__(
            application=app, decorated=False, resizable=False, title="EWidgets", css_classes=["ewidgets-blade"]
        )
        self._shell = ps.PantheonShell(self.get_display())
        self._panel: ps.Panel | None = None
        self._shown = 0.0  # 0 = concealed, 1 = fully revealed
        self._target = 0.0
        self._tween = Tween(self, self._set_shown)
        self._swipe: tuple[int, float] | None = None  # (direction, shown at swipe start) while fingers are down
        self._velocity = VelocityTracker()

        glass = Gtk.Overlay(
            css_classes=["blade-content"],
            margin_top=MARGIN_TOP,
            margin_bottom=MARGIN_BOTTOM,
            margin_start=MARGIN_SIDE,
            margin_end=MARGIN_SIDE,
        )
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=CARD_SPACING, css_classes=["blade-cards"])
        glass.set_child(content)
        glass.add_overlay(_Rim())
        for groups in rows:
            row = Gtk.Box(spacing=CARD_SPACING)
            for widgets in groups:
                group = Gtk.Box(spacing=CARD_SPACING, homogeneous=True)
                for widget in widgets:
                    widget.add_css_class("widget-card")
                    group.append(widget)
                row.append(group)
            content.append(row)
        self._slide = _Slide(glass)
        self.set_child(self._slide)

        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self._on_key_pressed)
        self.add_controller(keys)

        self.connect("realize", self._on_realize)
        self.connect("map", self._on_map)
        self.connect("notify::is-active", self._on_active_changed)
        self.connect("close-request", self._on_close_request)

        self._swipes = gestures.SwipeListener(
            SWIPE_FINGERS, self._on_swipe_begin, self._on_swipe_update, self._on_swipe_end
        )

    @property
    def revealed(self) -> bool:
        return self._target == 1

    def reveal(self) -> None:
        self._swipe = None
        self._show_window()
        self._animate_to(1)

    def conceal(self) -> None:
        self._swipe = None
        self._animate_to(0)

    def toggle(self) -> None:
        if self.revealed:
            self.conceal()
        else:
            self.reveal()

    def _show_window(self) -> None:
        if self._panel and self.get_mapped():
            self._panel.focus()
        else:
            self.present()  # _on_map asks Gala for focus

    def _hide_window(self) -> None:
        # Gala keeps the unmapped window around for its close animation, still
        # holding our wl_surface. Mapping that same surface again before then
        # gives the new window only Gala's blur: mutter can't attach the
        # surface, never sends it frame callbacks, and GTK stops drawing for
        # good. So each reveal gets a fresh surface (and panel object).
        self.set_visible(False)
        if self._panel:
            self._panel.destroy()
            self._panel = None
        self.unrealize()

    # Positioning

    def _set_shown(self, shown: float) -> None:
        was_concealed = self._shown == 0
        self._shown = shown
        self._slide.set_hidden(1 - shown)
        if (shown == 0) != was_concealed:
            self._update_input_region()
        if not self._panel:
            return
        # Gala's blur doesn't follow the content, so move it along.
        offset = self._slide.offset()
        top = max(MARGIN_TOP - offset, 0)
        bottom = MARGIN_BOTTOM + offset
        # Gala computes the blur's height as unsigned (height - top - bottom).
        # Insets that meet or cross wrap it to ~4 billion px and hang the compositor.
        if shown == 0 or top + bottom >= self._slide.get_height():
            self._panel.remove_blur()
        else:
            self._panel.add_blur(MARGIN_SIDE, MARGIN_SIDE, top, bottom, CORNER_RADIUS)

    def _animate_to(self, target: float) -> None:
        self._target = target
        self._tween.stop()
        distance = abs(target - self._shown)
        on_done = self._hide_window if target == 0 else None
        duration = max(SLIDE_DURATION_US * distance, MIN_SLIDE_DURATION_US)
        if not distance or not self._tween.start(self._shown, target, duration, on_done):
            self._set_shown(target)
            if on_done:
                on_done()

    # Swipes: down reveals, up conceals, and the blade tracks the fingers.

    def _on_swipe_begin(self, direction: int) -> None:
        if (direction == gestures.DOWN and self._shown < 1) or (direction == gestures.UP and self._shown > 0):
            self._tween.stop()
            self._swipe = (direction, self._shown)
            self._velocity.reset()
            self._show_window()
        elif direction == gestures.DOWN:
            self.conceal()  # swiping down again closes it too

    def _on_swipe_update(self, direction: int, fraction: float) -> None:
        if not self._swipe:
            return
        _, start = self._swipe
        distance = fraction * SWIPE_SENSITIVITY
        shown = start + distance if direction == gestures.DOWN else start - distance
        shown = min(max(shown, 0.0), 1.0)
        self._velocity.add(shown)
        self._set_shown(shown)

    def _on_swipe_end(self, direction: int, fraction: float) -> None:
        if not self._swipe:
            return
        self._on_swipe_update(direction, fraction)
        velocity = self._velocity.velocity()
        if abs(velocity) > FLICK_VELOCITY:
            finish_revealed = velocity > 0
        else:
            finish_revealed = self._shown >= 0.5
        if finish_revealed:
            self.reveal()
        else:
            self.conceal()

    # Window plumbing

    def _on_realize(self, _window: Gtk.Window) -> None:
        surface = self.get_surface()
        assert surface
        surface.connect("layout", lambda *_: self._update_input_region())

    def _update_input_region(self) -> None:
        # Only the glass takes input, so the margins don't block what's behind.
        # Nothing does while concealed.
        surface = self.get_surface()
        if not surface:
            return
        width, height = surface.get_width(), surface.get_height()
        region = cairo.Region()
        if self._shown > 0 and width > 2 * MARGIN_SIDE and height > MARGIN_TOP + MARGIN_BOTTOM:
            region = cairo.Region(
                cairo.RectangleInt(
                    MARGIN_SIDE, MARGIN_TOP, width - 2 * MARGIN_SIDE, height - MARGIN_TOP - MARGIN_BOTTOM
                )
            )
        surface.set_input_region(region)

    def _on_map(self, _window: Gtk.Window) -> None:
        # Must run before GTK commits the first buffer: Gala only positions a
        # panel when its window is first shown.
        surface = self.get_surface()
        assert surface
        self._panel = panel = self._shell.get_panel(surface)
        panel.set_anchor(ps.ANCHOR_TOP)
        panel.set_hide_mode(ps.HIDE_ALWAYS)
        self._set_shown(self._shown)
        panel.focus()
        # The window only exists on Gala's side once it has a buffer, so ask
        # again after the first frame in case the first request was too early.
        GLib.timeout_add(100, lambda: panel.focus() if panel is self._panel else None)

    def _on_active_changed(self, *_: object) -> None:
        # Clicking anywhere else conceals the blade.
        if not self.is_active() and self.revealed and not self._swipe:
            self.conceal()

    def _on_key_pressed(self, _ctrl: Gtk.EventControllerKey, keyval: int, _code: int, _state: Gdk.ModifierType) -> bool:
        if keyval == 0xFF1B:  # Escape
            self.conceal()
            return True
        return False

    def _on_close_request(self, _window: Gtk.Window) -> bool:
        self.conceal()
        return True
