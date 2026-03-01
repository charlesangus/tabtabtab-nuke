import os
import nuke

try:
    from PySide6 import QtGui
except ImportError:
    from PySide2 import QtGui

from tabtabtab import TabTabTabPlugin, launch


def _find_nuke_menu_items(menu, _path=None):
    """Extracts items from a given Nuke menu

    Returns a list of {'menuobj': ..., 'menupath': str} dicts.

    Ignores divider lines and hidden items (ones like "@;&CopyBranch" for shift+k)
    """
    found = []

    mi = list(menu.items())
    for i in mi:
        if isinstance(i, nuke.Menu):
            # Sub-menu, recurse
            mname = i.name().replace("&", "")
            subpath = "/".join(x for x in (_path, mname) if x is not None)

            if "ToolSets/Delete" in subpath:
                # Remove all ToolSets delete commands
                continue

            sub_found = _find_nuke_menu_items(menu=i, _path=subpath)
            found.extend(sub_found)
        elif isinstance(i, nuke.MenuItem):
            if i.name() == "":
                # Skip dividers
                continue
            if i.name().startswith("@;"):
                # Skip hidden items
                continue

            subpath = "/".join(x for x in (_path, i.name()) if x is not None)
            found.append({'menuobj': i, 'menupath': subpath})

    return found


class NukePlugin(TabTabTabPlugin):
    def get_items(self):
        return (_find_nuke_menu_items(nuke.menu("Nodes")) +
                _find_nuke_menu_items(nuke.menu("Nuke")))

    def get_weights_file(self):
        return os.path.expanduser("~/.nuke/tabtabtab_weights.json")

    def invoke(self, thing):
        thing['menuobj'].invoke()

    def get_icon(self, menuobj):
        icon_str = menuobj.icon()
        if not icon_str:
            return None
        # Search Nuke's plugin paths for the icon file
        for search_path in nuke.pluginPath():
            candidate = os.path.join(search_path, icon_str)
            if os.path.exists(candidate):
                return QtGui.QIcon(candidate)
        return None

    def get_color(self, menuobj):
        try:
            packed_color = nuke.defaultNodeColor(menuobj.name())
            if packed_color == 0:
                return (None, None)
            # Skip nodes whose colour comes from the global preference default
            # rather than a class-specific setting.  We detect this by comparing
            # against what Nuke returns for a class name that cannot exist.
            global_default_color = nuke.defaultNodeColor("__tabtabtab_sentinel__")
            if packed_color == global_default_color:
                return (None, None)
            r = (packed_color >> 24) & 0xFF
            g = (packed_color >> 16) & 0xFF
            b = (packed_color >> 8) & 0xFF
            # Use the un-dimmed tile colour as the left-block background (drawn
            # behind the icon) and as the text-area tint.
            tile_color = QtGui.QColor(r, g, b)
            return (tile_color, tile_color)
        except Exception:
            return (None, None)


_plugin = NukePlugin()

if nuke.NUKE_VERSION_MAJOR >= 9:
    _getParentMenu = lambda: nuke.menu("Node Graph")
else:
    _getParentMenu = lambda: nuke.menu("Nuke").findItem("Edit")


def registerNukeAction():
    menu = _getParentMenu()
    if menu.findItem("Tabtabtab") is None:
        menu.addCommand("Tabtabtab", lambda: launch(_plugin), "Tab")


def unregisterNukeAction():
    _getParentMenu().removeItem("Tabtabtab")
