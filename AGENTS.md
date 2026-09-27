# EWidgets

A widget blade for Pantheon (elementary OS 8, Wayland). It glides down from the
top of the screen on a three-finger swipe down and shows the weather plus
the playing song with previous / play-pause / next controls (any MPRIS player).
Below them, tiles toggle Do Not Disturb and dark mode and lock the screen,
next to two cards showing how much of your Claude Code and Codex plan limits
you have used, and a countdown timer.

Python + GTK 4 (PyGObject). No extra dependencies.

## Run

```sh
python3 -m ewidgets          # start in the background (blade stays hidden)
python3 -m ewidgets toggle   # also: show, hide, quit
bin/ewidgets-toggle          # fast toggle over D-Bus; starts the app if needed
```

Hide it with Escape, by clicking elsewhere, or by swiping down again.

## Weather

The weather comes from [Open-Meteo](https://open-meteo.com), with no API key.
Your location comes from GeoClue, or from your IP address if GeoClue can't
find it. To use a fixed city instead, create `~/.config/ewidgets/ewidgets.conf`:

```ini
[weather]
city=Kyiv
```

Swipe left or right with two fingers on the card (or click the dots) to switch
between the next 5 hours and the next 5 days.

## AI usage

The Claude and Codex cards show the 5-hour session and weekly limits with
when each resets. Claude's per-model weekly limits (Fable's) share the weekly
bar in a second colour, worked out from the OS accent in `core/theme.py`. They call the same
undocumented endpoints as the official CLIs, as
[ai-usagebar](https://github.com/akitaonrails/ai-usagebar) does, with the
login the CLI saved in `~/.claude/.credentials.json` or `~/.codex/auth.json`.
Those files are only read. When a token has expired, the card asks you to run
the CLI, which refreshes it. The cards refresh every 5 minutes while the blade
is open.

## Countdown

Turn the hours and minutes dials by dragging, scrolling (touchpad or mouse
wheel), clicking a number or with the arrow keys, then press start. The
countdown keeps running while the blade is hidden. When it ends, it shows a
desktop notification and plays a glassy ping.

## Gesture

`~/.config/touchegg/touchegg.conf` runs `bin/ewidgets-toggle` on a
three-finger swipe down. For Gala to ignore that swipe, the multitasking view
is moved to a four-finger swipe up (a Gala gesture setting). See
`docs/three-finger-swipe-down.md`.

## How it works

`ewidgets/core/pantheon_shell.py` is a small ctypes client for Gala's
`io_elementary_pantheon_shell_v1` protocol. It borrows GTK's Wayland
connection. The blade is a pantheon **panel** anchored `TOP` with hide mode
`ALWAYS`. Gala keeps such a panel slid out of view unless it is focused or
hovered, so the app shows the blade by requesting `panel.focus()`, and Gala runs
the slide animation. Blur comes from `panel.add_blur`.

Gala-specific details:

- `get_panel`/`set_anchor` must be sent while the window maps, before GTK
  commits the first buffer. Gala only positions a panel when it is first shown.
- `get_widget` exists in the protocol but does nothing in Gala 8.6.x.
- Once the blade has slid away, it is unmapped. Otherwise Gala's top-edge
  reveal barrier would pop it open whenever the pointer hits the wingpanel.

## Development

Linting is [Ruff](https://docs.astral.sh/ruff/), type checking is
[ty](https://docs.astral.sh/ty/), both through [uv](https://docs.astral.sh/uv/):

```sh
uv sync                   # dev tools and GTK 4 type stubs into .venv
uv run ruff format        # format the code
uv run ruff check         # add --fix for the safe fixes
uv run ty check
```

The app itself still runs on the system `python3` and its PyGObject;
the venv is only for the tools.

## Layout

```
ewidgets/
  app.py              Gtk.Application: single instance, show/hide/toggle actions;
                      picks the widgets and loads the styles
  core/               the blade itself; knows nothing about individual widgets
    blade.py          the panel window, its slide and show/hide lifecycle
    motion.py         eased animations and swipe velocity (also used by widgets)
    gestures.py       live three-finger swipes from the Touchégg daemon
    pantheon_shell.py ctypes Wayland protocol binding
    theme.py          loads the styles, follows the OS light/dark preference
    color.py          derives a second colour from the accent, for shared bars
  widgets/            one module or package per widget, plus shared pieces
    weather/          forecast.py fetches, conditions.py maps codes, widget.py draws
    ai_usage/         sources.py fetches Claude and Codex limits, widget.py draws
    countdown/        dial.py is the number wheel, alarm.py notifies and plays alarm.wav
    media_player.py
    tiles.py          square tiles: Do Not Disturb, dark mode, lock screen
    carousel.py       swipeable pages with dots
  styles/
    palette/          light.css and dark.css define every colour (@define-color)
    *.css             one stylesheet per component, using palette colours only
```

To add a widget: write a `Gtk.Widget` under `widgets/`, add it to one of the
groups in the rows passed to `WidgetBlade` in `app.py` (the blade puts it on
a card; cards in a group share one width), and
give it a stylesheet in `styles/`, which is picked up automatically. Use palette colours so dark mode just works.
