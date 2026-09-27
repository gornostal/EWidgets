# EWidgets - Widget Blade For Elementary OS

**Swipe down, see everything at a glance.**

Swipe down with three fingers on your
touchpad and it glides in from the top of the screen. Swipe again, press
Escape or click elsewhere, and it's gone.

![EWidgets demo](docs/media/ewidgets.avif)

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

## Make it yours

EWidgets isn't packaged as a .deb or a Flatpak, and that's on purpose.
The installer below puts the full source code in `~/.local/share/ewidgets`,
so you can use an AI agent to ✨ **infinitely customize** ✨ it. Open that folder in
Claude Code, Codex or any other coding agent and ask for what you want: a new
widget, a different layout, your own colours. [AGENTS.md](AGENTS.md) explains
the code to the agent, so it knows where everything goes. Restart
EWidgets to see the change.

## Install

You need elementary OS 8, logged in to the Secure Session (the default). In a
terminal, run:

```sh
wget -qO- https://raw.githubusercontent.com/gornostal/EWidgets/main/install.sh | bash
```

[The installer](install.sh):

- installs the few system packages EWidgets needs, such as GTK 4 for Python
  (it asks for your password only if something is missing)
- puts EWidgets in `~/.local/share/ewidgets` and starts it when you log in
- asks whether to open it with a three- or four-finger swipe down

Out of the box, a three-finger swipe up *or* down opens the Multitasking View.
If you pick three fingers, the installer offers to move the Multitasking View
to a four-finger swipe up, so the two don't fight. The swipe comes from
[Touchégg](https://github.com/JoseExposito/touchegg), which elementary OS 8
already runs.

To update, run the same command again. To open EWidgets without a touchpad,
bind `~/.local/share/ewidgets/bin/ewidgets toggle` to a keyboard shortcut in
System Settings → Keyboard → Shortcuts → Custom.

## For developers

How it works, the project layout and how to add your own widget are in
[AGENTS.md](AGENTS.md).

## License

[MIT](LICENSE)
