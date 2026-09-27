"""Now-playing info and transport controls for MPRIS media players."""

from typing import Any

from gi.repository import Gdk, Gio, GLib, Gtk, Pango

MPRIS_PREFIX = "org.mpris.MediaPlayer2."
MPRIS_PATH = "/org/mpris/MediaPlayer2"
PLAYER_IFACE = "org.mpris.MediaPlayer2.Player"
ART_SIZE = 72
# Fixed so the card keeps its size whatever the track, or with nothing playing.
TEXT_WIDTH_CHARS = 26


class MediaPlayer(Gtk.Box):
    def __init__(self) -> None:
        super().__init__(spacing=14, css_classes=["media-player"])
        self._bus = Gio.bus_get_sync(Gio.BusType.SESSION)
        self._players: dict[str, Gio.DBusProxy] = {}  # by bus name
        self._current: Gio.DBusProxy | None = None
        self._art_url: str | None = None

        self.art = Gtk.Image(
            icon_name="audio-x-generic-symbolic", pixel_size=32, css_classes=["album-art"], overflow=Gtk.Overflow.HIDDEN
        )
        self.art.set_size_request(ART_SIZE, ART_SIZE)
        self.append(self.art)

        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, valign=Gtk.Align.CENTER, hexpand=True)
        self.title = self._text_label(["track-title"])
        self.artist = self._text_label(["track-artist"])
        text.append(self.title)
        text.append(self.artist)
        self.append(text)

        controls = Gtk.Box(spacing=4, valign=Gtk.Align.CENTER)
        self.prev_btn = self._button("media-skip-backward-symbolic", "Previous", "Previous")
        self.play_btn = self._button("media-playback-start-symbolic", "Play/Pause", "PlayPause")
        self.play_btn.add_css_class("play-button")
        self.next_btn = self._button("media-skip-forward-symbolic", "Next", "Next")
        for b in (self.prev_btn, self.play_btn, self.next_btn):
            controls.append(b)
        self.append(controls)

        self._bus.signal_subscribe(
            "org.freedesktop.DBus",
            "org.freedesktop.DBus",
            "NameOwnerChanged",
            "/org/freedesktop/DBus",
            None,
            Gio.DBusSignalFlags.NONE,
            self._on_name_owner_changed,
        )
        names = self._bus.call_sync(
            "org.freedesktop.DBus",
            "/org/freedesktop/DBus",
            "org.freedesktop.DBus",
            "ListNames",
            None,
            GLib.VariantType("(as)"),
            Gio.DBusCallFlags.NONE,
            -1,
        ).unpack()[0]
        for name in names:
            if name.startswith(MPRIS_PREFIX):
                self._add_player(name)
        self._refresh()

    @staticmethod
    def _text_label(css_classes: list[str]) -> Gtk.Label:
        # width_chars == max_width_chars pins the width; single_line_mode keeps
        # the line height even when the label is empty.
        return Gtk.Label(
            xalign=0,
            ellipsize=Pango.EllipsizeMode.END,
            width_chars=TEXT_WIDTH_CHARS,
            max_width_chars=TEXT_WIDTH_CHARS,
            single_line_mode=True,
            css_classes=css_classes,
        )

    def _button(self, icon: str, tooltip: str, method: str) -> Gtk.Button:
        button = Gtk.Button(icon_name=icon, tooltip_text=tooltip, css_classes=["flat", "circular"])
        button.connect("clicked", lambda *_: self._call(method))
        return button

    # Player tracking

    def _on_name_owner_changed(
        self,
        _conn: Gio.DBusConnection,
        _sender: str | None,
        _path: str,
        _iface: str,
        _signal: str,
        params: GLib.Variant,
    ) -> None:
        name, _old, new = params.unpack()
        if not name.startswith(MPRIS_PREFIX):
            return
        if new:
            self._add_player(name)
        else:
            self._players.pop(name, None)
        self._refresh()

    def _add_player(self, name: str) -> None:
        Gio.DBusProxy.new(
            self._bus, Gio.DBusProxyFlags.NONE, None, name, MPRIS_PATH, PLAYER_IFACE, None, self._on_proxy_ready, name
        )

    def _on_proxy_ready(self, _source: object, result: Gio.AsyncResult, name: str) -> None:
        try:
            proxy = Gio.DBusProxy.new_finish(result)
        except GLib.Error:
            return
        proxy.connect("g-properties-changed", lambda *_: self._refresh())
        self._players[name] = proxy
        self._refresh()

    def _prop(self, name: str, default: Any = None, proxy: Gio.DBusProxy | None = None) -> Any:
        proxy = proxy or self._current
        value = proxy.get_cached_property(name) if proxy else None
        return value.unpack() if value is not None else default

    def _pick_player(self) -> Gio.DBusProxy | None:
        # Prefer something that is playing, then paused, then anything.
        rank = {"Playing": 0, "Paused": 1}
        players = sorted(self._players.values(), key=lambda p: rank.get(self._prop("PlaybackStatus", "Stopped", p), 2))
        if self._current in players and self._prop("PlaybackStatus") == "Playing":
            return self._current
        return players[0] if players else None

    # UI

    def _refresh(self) -> None:
        self._current = self._pick_player()
        if not self._current:
            self.title.set_label("Nothing playing")
            self.artist.set_label("")
            self._set_art(None)
            for b in (self.prev_btn, self.play_btn, self.next_btn):
                b.set_sensitive(False)
            return

        meta = self._prop("Metadata", {})
        title = meta.get("xesam:title") or "Unknown title"
        artists = meta.get("xesam:artist") or []
        self.title.set_label(title)
        self.artist.set_label(", ".join(artists) if isinstance(artists, list) else str(artists))
        self._set_art(meta.get("mpris:artUrl"))

        playing = self._prop("PlaybackStatus") == "Playing"
        self.play_btn.set_icon_name("media-playback-pause-symbolic" if playing else "media-playback-start-symbolic")
        self.prev_btn.set_sensitive(self._prop("CanGoPrevious", False))
        self.next_btn.set_sensitive(self._prop("CanGoNext", False))
        self.play_btn.set_sensitive(self._prop("CanPause", False) or self._prop("CanPlay", False))

    def _set_art(self, url: str | None) -> None:
        if url == self._art_url:
            return
        self._art_url = url
        if not url:
            self._set_placeholder_art()
            return
        Gio.File.new_for_uri(url).load_contents_async(None, self._on_art_loaded, url)

    def _on_art_loaded(self, file: Gio.File, result: Gio.AsyncResult, url: str) -> None:
        if url != self._art_url:
            return
        try:
            _ok, data, _etag = file.load_contents_finish(result)
            texture = Gdk.Texture.new_from_bytes(GLib.Bytes.new(data))
        except GLib.Error:
            self._set_placeholder_art()
            return
        self.art.set_from_paintable(texture)
        self.art.set_pixel_size(ART_SIZE)

    def _set_placeholder_art(self) -> None:
        self.art.set_from_icon_name("audio-x-generic-symbolic")
        self.art.set_pixel_size(32)

    def _call(self, method: str) -> None:
        if self._current:
            self._current.call(method, None, Gio.DBusCallFlags.NONE, -1, None, None)
