# EWidgets - Widget Blade For Elementary OS

**Swipe down, see everything at a glance.**

Swipe down with three fingers on your
touchpad and it glides in from the top of the screen. Swipe again, press
Escape or click elsewhere, and it's gone.

<!-- TODO: screenshot -->

## What's inside

- 🌤️ **Weather.** The next 5 hours or the next 5 days, for wherever you are.
  No account or API key needed.
- 🎵 **Now playing.** The current song with play, pause and skip, whether it's
  Spotify, your browser or any other music player.
- 🌙 **Quick toggles.** Do Not Disturb, dark mode and lock screen, one tap each.
- 🤖 **AI usage.** How much of your Claude Code and Codex plan limits you've
  used, and when they reset.
- ⏲️ **Countdown timer.** Spin the dials, press start, and get a ping when
  time's up, even with the panel closed.

It follows your system's light or dark theme and accent colour, so it looks
like it belongs there.

## Try it

You need elementary OS 8. Everything else is already on your system.

```sh
git clone https://github.com/gornostal/EWidgets.git
cd EWidgets
python3 -m ewidgets show
```

### Set up the swipe

The swipe comes from [Touchégg](https://github.com/JoseExposito/touchegg),
which elementary OS 8 already runs. Add this inside `<application name="All">`
in `~/.config/touchegg/touchegg.conf`, with the path to your copy of EWidgets:

```xml
<gesture type="SWIPE" fingers="3" direction="DOWN">
  <action type="RUN_COMMAND">
    <repeat>false</repeat>
    <command>/path/to/EWidgets/bin/ewidgets-toggle</command>
    <on>begin</on>
  </action>
</gesture>
```

Then restart Touchégg with `pkill -x touchegg; touchegg &`, or log out and back in.

**Heads-up:** out of the box, a three-finger swipe (up *or* down) opens the
Multitasking View, so the two will fight. Move one of them to four fingers.
To move the Multitasking View, which is what I recommend:

```sh
gsettings set io.elementary.desktop.wm.gestures four-finger-swipe-up multitasking-view
gsettings set io.elementary.desktop.wm.gestures three-finger-swipe-up none
```

If you'd rather open EWidgets with four fingers, set `fingers="4"` in the
Touchégg config above and `SWIPE_FINGERS = 4` in `ewidgets/core/blade.py`.

The full details are in [the gesture notes](docs/three-finger-swipe-down.md).

### Pick your city

The weather finds your location on its own. To pin it to a city, create
`~/.config/ewidgets/ewidgets.conf`:

```ini
[weather]
city=Kyiv
```

## For developers

How it works, the project layout and how to add your own widget are in
[AGENTS.md](AGENTS.md).

## License

[MIT](LICENSE)
