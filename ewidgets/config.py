"""Settings from ~/.config/ewidgets/ewidgets.conf, a key file such as:

[gesture]
fingers=4
"""

from pathlib import Path

from gi.repository import GLib

CONFIG_PATH = Path(GLib.get_user_config_dir()) / "ewidgets" / "ewidgets.conf"


def _load() -> GLib.KeyFile | None:
    keyfile = GLib.KeyFile()
    try:
        keyfile.load_from_file(str(CONFIG_PATH), GLib.KeyFileFlags.NONE)
    except GLib.Error:
        return None
    return keyfile


def get_int(group: str, key: str, default: int) -> int:
    keyfile = _load()
    if not keyfile:
        return default
    try:
        return keyfile.get_integer(group, key)
    except GLib.Error:
        return default
