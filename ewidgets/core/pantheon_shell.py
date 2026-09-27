"""Minimal ctypes client for Gala's io_elementary_pantheon_shell_v1 protocol.

GTK owns the Wayland connection, so we borrow its wl_display and wl_surface
pointers and send pantheon-shell requests on a private event queue.
Protocol: https://github.com/elementary/gala/blob/main/protocol/pantheon-desktop-shell-v1.xml
"""

import ctypes
import ctypes.util
from collections.abc import Sequence
from ctypes import POINTER, Structure, Union, c_char_p, c_int, c_int32, c_uint32, c_void_p

from gi.repository import GObject

_wl = ctypes.CDLL(ctypes.util.find_library("wayland-client") or "libwayland-client.so.0")
_gtk = ctypes.CDLL("libgtk-4.so.1")


class wl_message(Structure):
    pass


class wl_interface(Structure):
    pass


wl_message._fields_ = [("name", c_char_p), ("signature", c_char_p), ("types", POINTER(POINTER(wl_interface)))]
wl_interface._fields_ = [
    ("name", c_char_p),
    ("version", c_int),
    ("method_count", c_int),
    ("methods", POINTER(wl_message)),
    ("event_count", c_int),
    ("events", POINTER(wl_message)),
]


class wl_argument(Union):
    _fields_ = [("i", c_int32), ("u", c_uint32), ("s", c_char_p), ("o", c_void_p), ("n", c_uint32)]


_wl.wl_display_create_queue.restype = c_void_p
_wl.wl_display_create_queue.argtypes = [c_void_p]
_wl.wl_proxy_create_wrapper.restype = c_void_p
_wl.wl_proxy_create_wrapper.argtypes = [c_void_p]
_wl.wl_proxy_wrapper_destroy.argtypes = [c_void_p]
_wl.wl_proxy_set_queue.argtypes = [c_void_p, c_void_p]
_wl.wl_proxy_add_listener.argtypes = [c_void_p, c_void_p, c_void_p]
_wl.wl_proxy_marshal_array.argtypes = [c_void_p, c_uint32, POINTER(wl_argument)]
_wl.wl_proxy_marshal_array_constructor.restype = c_void_p
_wl.wl_proxy_marshal_array_constructor.argtypes = [c_void_p, c_uint32, POINTER(wl_argument), c_void_p]
_wl.wl_proxy_marshal_array_constructor_versioned.restype = c_void_p
_wl.wl_proxy_marshal_array_constructor_versioned.argtypes = [
    c_void_p,
    c_uint32,
    POINTER(wl_argument),
    c_void_p,
    c_uint32,
]
_wl.wl_proxy_destroy.argtypes = [c_void_p]
_wl.wl_display_roundtrip_queue.argtypes = [c_void_p, c_void_p]
_wl.wl_display_flush.argtypes = [c_void_p]

_gtk.gdk_wayland_display_get_wl_display.restype = c_void_p
_gtk.gdk_wayland_display_get_wl_display.argtypes = [c_void_p]
_gtk.gdk_wayland_surface_get_wl_surface.restype = c_void_p
_gtk.gdk_wayland_surface_get_wl_surface.argtypes = [c_void_p]

_wl_registry_interface = wl_interface.in_dll(_wl, "wl_registry_interface")
_wl_surface_interface = wl_interface.in_dll(_wl, "wl_surface_interface")

_keepalive: list[object] = []  # ctypes objects referenced from C must outlive this module's users


type _MessageSpec = tuple[str, str, Sequence[wl_interface | None]]


def _messages(specs: Sequence[_MessageSpec]) -> ctypes.Array[wl_message]:
    """specs: [(name, signature, [interface or None, ...]), ...]"""
    arr = (wl_message * len(specs))()
    for i, (name, sig, types) in enumerate(specs):
        t = (POINTER(wl_interface) * max(len(types), 1))()
        for j, iface in enumerate(types):
            t[j] = ctypes.pointer(iface) if iface is not None else None
        _keepalive.append(t)
        arr[i] = wl_message(name.encode(), sig.encode(), ctypes.cast(t, POINTER(POINTER(wl_interface))))
    _keepalive.append(arr)
    return arr


def _set_interface(iface: wl_interface, name: str, methods: Sequence[_MessageSpec]) -> None:
    iface.name = name.encode()
    iface.version = 1
    iface.method_count = len(methods)
    iface.methods = ctypes.cast(_messages(methods), POINTER(wl_message))
    iface.event_count = 0
    iface.events = None


shell_iface = wl_interface()
panel_iface = wl_interface()
widget_iface = wl_interface()
extended_iface = wl_interface()
greeter_iface = wl_interface()
_keepalive += [shell_iface, panel_iface, widget_iface, extended_iface, greeter_iface]

# Method order defines the opcodes, so it must match the protocol XML.
_set_interface(
    shell_iface,
    "io_elementary_pantheon_shell_v1",
    [
        ("get_panel", "no", [panel_iface, _wl_surface_interface]),
        ("get_widget", "no", [widget_iface, _wl_surface_interface]),
        ("get_extended_behavior", "no", [extended_iface, _wl_surface_interface]),
        ("get_greeter", "no", [greeter_iface, _wl_surface_interface]),
    ],
)
_set_interface(
    panel_iface,
    "io_elementary_pantheon_panel_v1",
    [
        ("destroy", "", []),
        ("set_anchor", "u", [None]),
        ("focus", "", []),
        ("set_size", "ii", [None, None]),
        ("set_hide_mode", "u", [None]),
        ("request_visible_in_multitasking_view", "", []),
        ("add_blur", "uuuuu", [None] * 5),
        ("remove_blur", "", []),
    ],
)
_set_interface(widget_iface, "io_elementary_pantheon_widget_v1", [("destroy", "", [])])
_set_interface(
    extended_iface,
    "io_elementary_pantheon_extended_behavior_v1",
    [
        ("destroy", "", []),
        ("set_keep_above", "", []),
        ("make_centered", "", []),
        ("focus", "", []),
        ("make_modal", "u", [None]),
        ("make_monitor_label", "i", [None]),
    ],
)
_set_interface(greeter_iface, "io_elementary_pantheon_greeter_v1", [("destroy", "", []), ("make_greeter", "", [])])

ANCHOR_TOP, ANCHOR_BOTTOM, ANCHOR_LEFT, ANCHOR_RIGHT = range(4)
HIDE_NEVER, HIDE_MAXIMIZED_FOCUS_WINDOW, HIDE_OVERLAPPING_FOCUS_WINDOW, HIDE_OVERLAPPING_WINDOW, HIDE_ALWAYS = range(5)

_GLOBAL_CB = ctypes.CFUNCTYPE(None, c_void_p, c_void_p, c_uint32, c_char_p, c_uint32)
_GLOBAL_REMOVE_CB = ctypes.CFUNCTYPE(None, c_void_p, c_void_p, c_uint32)


class _RegistryListener(Structure):
    _fields_ = [("global_", _GLOBAL_CB), ("global_remove", _GLOBAL_REMOVE_CB)]


def _gpointer(gobject: GObject.Object) -> int | None:
    get = ctypes.pythonapi.PyCapsule_GetPointer
    get.restype = c_void_p
    get.argtypes = [ctypes.py_object, c_char_p]
    return get(gobject.__gpointer__, None)  # ty: ignore[unresolved-attribute]  (PyGObject internal, not in stubs)


def _args(*values: tuple[str, object]) -> ctypes.Array[wl_argument]:
    arr = (wl_argument * max(len(values), 1))()
    for i, (field, value) in enumerate(values):
        setattr(arr[i], field, value)
    return arr


class Panel:
    def __init__(self, shell: "PantheonShell", proxy: int | None) -> None:
        self._shell = shell
        self._proxy = proxy

    def _call(self, opcode: int, *args: tuple[str, object]) -> None:
        _wl.wl_proxy_marshal_array(self._proxy, opcode, _args(*args))
        self._shell.flush()

    def set_anchor(self, anchor: int) -> None:
        self._call(1, ("u", anchor))

    def focus(self) -> None:
        self._call(2)

    def set_size(self, width: int, height: int) -> None:
        self._call(3, ("i", width), ("i", height))

    def set_hide_mode(self, mode: int) -> None:
        self._call(4, ("u", mode))

    def request_visible_in_multitasking_view(self) -> None:
        self._call(5)

    def add_blur(self, left: int, right: int, top: int, bottom: int, clip_radius: int) -> None:
        self._call(6, *(("u", v) for v in (left, right, top, bottom, clip_radius)))

    def remove_blur(self) -> None:
        self._call(7)

    def destroy(self) -> None:
        _wl.wl_proxy_marshal_array(self._proxy, 0, _args())
        _wl.wl_proxy_destroy(self._proxy)
        self._shell.flush()


class PantheonShell:
    """Binds io_elementary_pantheon_shell_v1 on GTK's Wayland connection."""

    def __init__(self, gdk_display: GObject.Object) -> None:
        self.display = _gtk.gdk_wayland_display_get_wl_display(_gpointer(gdk_display))
        if not self.display:
            raise RuntimeError("Not running on a Wayland display")

        self._queue = _wl.wl_display_create_queue(self.display)
        wrapper = _wl.wl_proxy_create_wrapper(self.display)
        _wl.wl_proxy_set_queue(wrapper, self._queue)
        # wl_display.get_registry is opcode 1
        self._registry = _wl.wl_proxy_marshal_array_constructor(
            wrapper, 1, _args(("n", 0)), ctypes.addressof(_wl_registry_interface)
        )
        _wl.wl_proxy_wrapper_destroy(wrapper)

        self._shell: int | None = None
        self._listener = _RegistryListener(_GLOBAL_CB(self._on_global), _GLOBAL_REMOVE_CB(lambda *a: None))
        _wl.wl_proxy_add_listener(self._registry, ctypes.addressof(self._listener), None)
        _wl.wl_display_roundtrip_queue(self.display, self._queue)

        if not self._shell:  # ty: ignore[redundant-condition]  (_on_global sets it during the roundtrip)
            raise RuntimeError("Compositor does not offer io_elementary_pantheon_shell_v1 (not Gala?)")

    def _on_global(
        self, _data: int | None, registry: int | None, name: int, interface: bytes | None, version: int
    ) -> None:
        if interface == b"io_elementary_pantheon_shell_v1" and not self._shell:
            # wl_registry.bind is opcode 0, signature "usun"
            self._shell = _wl.wl_proxy_marshal_array_constructor_versioned(
                registry, 0, _args(("u", name), ("s", interface), ("u", 1), ("n", 0)), ctypes.addressof(shell_iface), 1
            )

    def flush(self) -> None:
        _wl.wl_display_flush(self.display)

    def get_panel(self, gdk_surface: GObject.Object) -> Panel:
        wl_surface = _gtk.gdk_wayland_surface_get_wl_surface(_gpointer(gdk_surface))
        proxy = _wl.wl_proxy_marshal_array_constructor(
            self._shell, 0, _args(("n", 0), ("o", wl_surface)), ctypes.addressof(panel_iface)
        )
        self.flush()
        return Panel(self, proxy)
