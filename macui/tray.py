"""The menu bar extras, the way macOS calls them.

Applications that want to sit in the menu bar publish themselves on the
session bus as StatusNotifierItem, and the shell answers as their host
under the name org.kde.StatusNotifierWatcher.  Every item carries an
icon of its own -- either the name of one in the theme, or the pixels
themselves -- and a menu behind it.

The protocol is the one KDE drew up; the shell speaks the parts of it
waybar and cairo-dock speak as well, so the tray programs written for
their shelves -- and the appindicators of GNOME -- show up here
untouched.
"""

from __future__ import annotations

import os
import sys

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")

from gi.repository import GdkPixbuf, Gio, GLib, Gtk  # noqa: E402

from . import apps, draw  # noqa: E402

WATCHER_NAME = "org.kde.StatusNotifierWatcher"
WATCHER_PATH = "/StatusNotifierWatcher"
ITEM_INTERFACE = "org.kde.StatusNotifierItem"
MENU_INTERFACE = "com.canonical.dbusmenu"
DEFAULT_PATH = "/StatusNotifierItem"

WATCHER_XML = """
<node>
  <interface name="org.kde.StatusNotifierWatcher">
    <method name="RegisterStatusNotifierItem">
      <arg name="serviceOrPath" type="s" direction="in"/>
    </method>
    <method name="RegisterStatusNotifierHost">
      <arg name="service" type="s" direction="in"/>
    </method>
    <property name="RegisteredStatusNotifierItems" type="as" access="read"/>
    <property name="IsStatusNotifierHostRegistered" type="b" access="read"/>
    <property name="ProtocolVersion" type="i" access="read"/>
    <signal name="StatusNotifierItemRegistered">
      <arg type="s"/>
    </signal>
    <signal name="StatusNotifierItemUnregistered">
      <arg type="s"/>
    </signal>
    <signal name="StatusNotifierHostRegistered"/>
  </interface>
</node>
"""


def _bus():
    try:
        return Gio.bus_get_sync(Gio.BusType.SESSION, None)
    except GLib.Error:
        return None


def _read_property(connection, service, path, name):
    """Read one property of an item, with the answer unpacked."""
    try:
        reply = connection.call_sync(
            service, path, "org.freedesktop.DBus.Properties", "Get",
            GLib.Variant("(ss)", (ITEM_INTERFACE, name)),
            GLib.VariantType("(v)"), Gio.DBusCallFlags.NONE, 1500, None)
        return reply.unpack()[0]
    except GLib.Error:
        return None


def pixbuf_from_argb(raw, width, height):
    """Turn the ARGB bytes of an item's pixmap into a pixbuf.

    The protocol sends ARGB32 with the alpha in the first byte; cairo
    wants it in the last one, so the channels are turned around while
    the pixels are copied into the pixbuf, row by row.
    """
    try:
        need = width * height * 4
        data = bytes(raw)[:need]
        if len(data) < need:
            return None
        pb = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, True, 8,
                                  width, height)
        stride = pb.get_rowstride()
        pixels = bytearray(memoryview(pb.get_pixels()))
        for y in range(height):
            start = y * width * 4
            row = bytearray(width * 4)
            row[0::4] = data[start + 1:start + 4:1]
            row[1::4] = data[start + 2:start + 4:1]
            row[2::4] = data[start + 3:start + 4:1]
            row[3::4] = data[start:start + 4:1]
            offset = y * stride
            pixels[offset:offset + len(row)] = row
        return GdkPixbuf.Pixbuf.new_from_data(
            bytes(pixels), GdkPixbuf.Colorspace.RGB, True, 8,
            width, height, stride, None, None)
    except Exception:  # noqa: BLE001
        return None


class TrayItem:
    """One application that sits in the menu bar."""

    def __init__(self, connection, service, path):
        self.service = service
        self.path = path
        self.id = ""
        self.title = ""
        self.status = "Active"
        self.icon_name = ""
        self.attention_name = ""
        self.pixmap = None
        self.attention_pixmap = None
        self.is_menu = False
        self.menu_path = ""
        self.key = f"{service}{path}"
        self._cache: dict = {}
        self.refresh(connection)

    def refresh(self, connection):
        self._cache.clear()
        self.id = _read_property(connection, self.service, self.path,
                                 "Id") or ""
        self.title = _read_property(connection, self.service, self.path,
                                    "Title") or ""
        status = _read_property(connection, self.service, self.path, "Status")
        if status:
            self.status = status
        self.icon_name = _read_property(connection, self.service, self.path,
                                        "IconName") or ""
        self.attention_name = _read_property(connection, self.service,
                                             self.path,
                                             "AttentionIconName") or ""
        is_menu = _read_property(connection, self.service, self.path,
                                 "ItemIsMenu")
        self.is_menu = bool(is_menu)
        self.menu_path = _read_property(connection, self.service, self.path,
                                        "Menu") or ""
        self.pixmap = self._pixbuf_of(
            _read_property(connection, self.service, self.path,
                           "IconPixmap"))
        self.attention_pixmap = self._pixbuf_of(
            _read_property(connection, self.service, self.path,
                           "AttentionIconPixmap"))

    def _pixbuf_of(self, pixels):
        """The biggest pixmap of the item, if it sent its pixels."""
        try:
            best = None
            for width, height, raw in pixels[-1]:
                if width <= 0 or height <= 0:
                    continue
                if best is None or width * height > best[0]:
                    best = (width * height, width, height, raw)
            if best is None:
                return None
            return pixbuf_from_argb(best[3], best[1], best[2])
        except Exception:  # noqa: BLE001
            return None

    def has_icon(self):
        return bool(self.icon_name) or self.pixmap is not None

    def pixbuf(self, size):
        """The icon of the item, at the size the menu bar asks for."""
        name = self.icon_name
        if self.status == "NeedsAttention":
            if self.attention_name:
                name = self.attention_name
            elif self.attention_pixmap is not None:
                return self.attention_pixmap
        if name:
            key = (name, self.status, round(size))
            if key in self._cache:
                return self._cache[key]
            path = None
            icon_theme = Gtk.IconTheme.get_default()
            icon_theme.append_search_path(
                os.path.expanduser("~/.local/share/icons/WhiteSur"))
            icon = icon_theme.lookup_icon(name, int(size * 2),
                                          Gtk.IconLookupFlags.FORCE_SIZE)
            if icon is not None:
                path = icon.get_filename()
            if path is None:
                path = apps.icon_path(name)
            if path is None:
                path = draw.bundled_icon_path(name)
            pixbuf = draw.load_icon(path) if path else None
            if pixbuf is not None:
                self._cache[key] = pixbuf
                return pixbuf
        return self.pixmap

    def activate(self, connection):
        """The click of the primary button."""
        self._call(connection, "Activate")
        return True

    def _call(self, connection, method):
        try:
            connection.call_sync(
                self.service, self.path, ITEM_INTERFACE, method,
                GLib.Variant("(ii)", (0, 0)), GLib.VariantType("()"),
                Gio.DBusCallFlags.NONE, 2000, None)
        except GLib.Error:
            pass

    def context_menu(self, connection):
        """Ask the item to show its own menu at the point."""
        self._call(connection, "ContextMenu")
        return True

    def menu_rows(self):
        """The rows of the item's menu, read from com.canonical.dbusmenu."""
        return _menu_rows(self.service, self.menu_path)

    def click_menu_item(self, item_id):
        """The click of one row inside the item's menu."""
        _menu_click(self.service, self.menu_path, item_id)


def _menu_rows(service, path):
    """The rows of the menu of an item, flattened.

    The layout comes as a tree; only the rows that sell something are
    kept, and the deeper ones sink to the bottom of the list, the way
    macOS shows menu items only outside of the branch.
    """
    bus = _bus()
    if bus is None or not path:
        return []
    try:
        reply = bus.call_sync(
            service, path, MENU_INTERFACE, "GetLayout",
            GLib.Variant("(iias)", (0, 3, [])),
            GLib.VariantType("(u(ia{sv}av))"), Gio.DBusCallFlags.NONE,
            2000, None)
    except GLib.Error:
        return []
    _revision, layout = reply.unpack()
    rows = []
    _walk_menu(layout[2], rows, depth=0)
    return rows


def _walk_menu(children, rows, depth):
    for entry in children or []:
        item_id, props = entry[0], entry[1] or {}
        label = str(props.get("label", "") or "")
        kind = str(props.get("type", "standard") or "standard")
        visible = bool(props.get("visible", True))
        if not visible:
            continue
        if kind == "separator":
            label = "---"
        elif not label:
            label = str(props.get("slot-key", "") or "")
        if label and label != "---":
            rows.append({
                "id": item_id,
                "label": label,
                "enabled": bool(props.get("enabled", True)),
                "depth": depth,
            })
        _walk_menu(entry[2], rows, depth=depth + 1)


def _menu_click(service, path, item_id):
    bus = _bus()
    if bus is None or not path or item_id is None:
        return
    try:
        bus.call_sync(service, path, MENU_INTERFACE, "Event",
                      GLib.Variant("(isvu)",
                                   (int(item_id), 0,
                                    GLib.Variant("s", ""), 0)),
                      GLib.VariantType("()"), Gio.DBusCallFlags.NONE,
                      2000, None)
    except GLib.Error:
        pass


class Tray:
    """The host: the name org.kde.StatusNotifierWatcher belongs to it."""

    def __init__(self, change_callback=None):
        self.items: list[TrayItem] = []
        self._changed = change_callback
        self._bus_id = 0
        self._connection = _bus()
        if self._connection is None:
            return
        self._own()
        self._discover()
        self._connection.signal_subscribe(
            "org.freedesktop.DBus", "org.freedesktop.DBus",
            "NameOwnerChanged", "/org/freedesktop/DBus", None,
            Gio.DBusSignalFlags.NONE, self._on_name_owner_changed, None)

    # -- owning the name ----------------------------------------------------

    def _own(self):
        connection = self._connection

        def method_call(_connection, _sender, _path, _interface, method,
                        params, invocation):
            if method == "RegisterStatusNotifierItem":
                self._register_item(_connection, _sender, params)
                try:
                    invocation.return_value(None)
                except Exception:  # noqa: BLE001
                    pass
                return
            if method == "RegisterStatusNotifierHost":
                try:
                    invocation.return_value(None)
                except Exception:  # noqa: BLE001
                    pass
                return
            if method == "GetAll":
                name = _interface.split(".", 4)[-1]
                values = []
                for prop in self._info().properties:
                    value = get_property(_connection, _sender, _path,
                                         _interface, prop.name)
                    if value is not None:
                        values.append((prop.name,
                                       GLib.Variant(prop.signature, value)))
                try:
                    invocation.return_value(
                        GLib.Variant("(a{sv})", (dict(values),)))
                except Exception:  # noqa: BLE001
                    pass
                return
            if method == "Get":
                interface_name, property_name = params.unpack()
                if property_name.startswith("Registered"):
                    try:
                        invocation.return_value(GLib.Variant(
                            "(v)",
                            (GLib.Variant("as",
                                          [item.key for item in self.items]),)))
                    except Exception:  # noqa: BLE001
                        pass
                    return
                prop = next((p for p in self._info().properties
                             if p.name == property_name), None)
                if prop is None:
                    try:
                        invocation.return_dbus_error(
                            "org.freedesktop.DBus.Error.InvalidArgs",
                            f"No such property {property_name}")
                    except Exception:  # noqa: BLE001
                        pass
                    return
                value = get_property(_connection, _sender, _path,
                                     interface_name, property_name)
                try:
                    invocation.return_value(GLib.Variant(
                        "(v)", (GLib.Variant(prop.signature, value),)))
                except Exception:  # noqa: BLE001
                    pass
                return
            # Set: read only for us
            try:
                invocation.return_value(None)
            except Exception:  # noqa: BLE001
                pass

        def get_property(_connection, _sender, _path, _interface, name):
            if name == "RegisteredStatusNotifierItems":
                return GLib.Variant("as", [item.key for item in self.items])
            if name == "IsStatusNotifierHostRegistered":
                return GLib.Variant("b", True)
            if name == "ProtocolVersion":
                return GLib.Variant("i", 0)
            return None

        try:
            info = Gio.DBusNodeInfo.new_for_xml(WATCHER_XML).interfaces[0]
            connection.register_object(WATCHER_PATH, info,
                                       method_call, get_property, None)
        except GLib.Error as exc:
            print(f"macshell: the tray watcher could not be registered: "
                  f"{exc}", file=sys.stderr, flush=True)
        try:
            # the name itself, and on the same connection the interface
            # sits on, or the programs of the tray would knock at a door
            # where nobody lives
            Gio.bus_own_name_on_connection(
                connection, WATCHER_NAME, Gio.BusNameOwnerFlags.NONE)
        except GLib.Error:
            pass
        try:
            connection.emit_signal(None, WATCHER_PATH, WATCHER_NAME,
                                   "StatusNotifierHostRegistered", None)
        except GLib.Error:
            pass

    def _register_item(self, connection, sender, params):
        """An application announced itself to the watcher.

        The legwork happens on the next idle: answering a bus call by
        making more bus calls on the same connection would wait for the
        answer of a call that is still standing.
        """
        value = params.unpack()[0] or ""
        if value.startswith("/"):
            service, path = sender, value
        else:
            service, path = value, DEFAULT_PATH
        GLib.idle_add(self._add_item, service, path)
        return True

    def _add_item(self, service, path):
        self._add(self._connection, service, path)
        return False

    # -- discovering the items ---------------------------------------------

    def _discover(self):
        """The items that registered while nobody hosted them yet."""
        if self._connection is None:
            return
        try:
            names = self._connection.call_sync(
                "org.freedesktop.DBus", "/org/freedesktop/DBus",
                "org.freedesktop.DBus", "ListNames", None,
                GLib.VariantType("(as)"), Gio.DBusCallFlags.NONE, 2000,
                None)
        except GLib.Error:
            return
        for name in names.unpack()[0]:
            if name.startswith("org.kde.StatusNotifierItem-"):
                self._add(self._connection, name, DEFAULT_PATH)

    def _add(self, connection, service, path):
        key = f"{service}{path}"
        if any(item.key == key for item in self.items):
            return
        item = TrayItem(connection, service, path)
        if not item.has_icon():
            return
        self.items = [i for i in self.items if i.key != key] + [item]
        self._emit("StatusNotifierItemRegistered", key)
        if self._changed:
            self._changed()

    def _on_name_owner_changed(self, _connection, _sender, _path,
                               _interface, _signal, params, _data):
        try:
            name, _before, after = params.unpack()
        except Exception:  # noqa: BLE001
            return
        if name.startswith("org.kde.StatusNotifierItem-") and after == "":
            before = len(self.items)
            self.items = [item for item in self.items
                          if item.service != name]
            if len(self.items) != before:
                self._emit("StatusNotifierItemUnregistered", name)
                if self._changed:
                    self._changed()

    def on_change(self, callback):
        """What to call when the collection of items changed."""
        self._changed = callback

    def _emit(self, signal, value):
        try:
            self._connection.emit_signal(
                None, WATCHER_PATH, WATCHER_NAME, signal,
                GLib.Variant("(s)", (value or "",)))
        except GLib.Error:
            pass

    def refresh(self):
        """The items are asked to refresh their icons."""
        for item in list(self.items):
            try:
                item.refresh(self._connection)
            except Exception:  # noqa: BLE001
                pass

    # -- rendering and the clicks of the user ------------------------------

    def order(self):
        """Every item, the ones that want attention first."""
        rank = {"NeedsAttention": 0, "Active": 1, "Passive": 2}
        return sorted(self.items, key=lambda item: rank.get(item.status, 1))

    def activate(self, index):
        items = self.order()
        if 0 <= index < len(items):
            return items[index].activate(self._connection)
        return False
