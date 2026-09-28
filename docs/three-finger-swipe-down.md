# Three-finger swipe down on elementary OS 8

## Why it does nothing

On elementary OS 8 (Pantheon, Wayland), the window manager Gala only offers
these touchpad gestures (`io.elementary.desktop.wm.gestures`):

| Key                             | Current value       |
| ------------------------------- | ------------------- |
| `three-finger-swipe-up`         | `multitasking-view` |
| `three-finger-swipe-horizontal` | `switch-windows`    |
| `three-finger-pinch`            | `none`              |
| `four-finger-swipe-up`          | `none`              |
| `four-finger-swipe-horizontal`  | `none`              |
| `four-finger-pinch`             | `none`              |

Allowed values: `none`, `multitasking-view`, `toggle-maximized` (and
`switch-to-workspace`, `move-to-workspace`, `switch-windows` for the
horizontal swipes).

Gala has no key for three-finger swipe down. However, when
`three-finger-swipe-up` is `multitasking-view`, Gala binds **both** vertical
directions to that gesture (`lib/Gestures/GestureSettings.vala`). Swiping down
then plays the overview's "overshoot" animation on open windows.

**Fix used here:** the multitasking view moves to four fingers, so three-finger
vertical swipes are free:

```sh
gsettings set io.elementary.desktop.wm.gestures four-finger-swipe-up multitasking-view
gsettings set io.elementary.desktop.wm.gestures three-finger-swipe-up none
```

Horizontal swipes don't get in the way, so `three-finger-swipe-horizontal`
can stay as it is (`switch-to-workspace` switches workspaces).

## Binding it with Touchégg

Touchégg (v2.0.17) is already installed:

- `touchegg.service` (daemon) is enabled and running.
- The client (`/usr/bin/touchegg`) is started with the session and connects to
  the daemon.
- Config file: `~/.config/touchegg/touchegg.conf`. It has no gestures defined
  yet.

With the fix above, Gala no longer reacts to three-finger vertical swipes.

EWidgets doesn't need a gesture in `touchegg.conf`: the daemon broadcasts
every gesture over D-Bus as it happens (see `ewidgets/core/gestures.py`), and
the blade follows it. A `RUN_COMMAND` gesture that toggles the blade, as
earlier versions used, would fight with that, so `install.sh` removes it.

For other commands, add a gesture like this inside `<application name="All">`:

```xml
<gesture type="SWIPE" fingers="3" direction="DOWN">
  <action type="RUN_COMMAND">
    <repeat>false</repeat>
    <command>your-command-here</command>
    <on>begin</on>
  </action>
</gesture>
```

Then restart the client:

```sh
pkill -u "$USER" -x touchegg; touchegg &
```

(or log out and back in).

## Wayland limits

- **`RUN_COMMAND` works reliably.** It just runs a program.
- **`SEND_KEYS`** (sending a keyboard shortcut) and the window actions
  (`MINIMIZE_WINDOW`, `MAXIMIZE_RESTORE_WINDOW`, and so on) use X11. On
  Wayland they only affect XWayland apps, not native Wayland windows.
- To trigger a keyboard shortcut on any window, use `RUN_COMMAND` with
  `ydotool` or `wtype` instead.
- **Minimize the focused window:** Gala doesn't expose a command for this, so
  the simplest route is `ydotool` sending the system's minimize shortcut.
