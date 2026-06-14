"""Tests for the Nuke menu fingerprint and the split between full
cache invalidation and colour-only invalidation.

Covers:
  - _menu_fingerprint recurses the full tree, so a deep change (below the
    old depth-2 bound) produces a different fingerprint. This is what lets
    TabTabTabWidget drop the unconditional per-open re-walk and still catch
    deep mid-session menu installs (issue #11).
  - NukePlugin.invalidate_color_cache clears only colour memoisation,
    leaving the item + fingerprint cache intact (so an unchanged menu set
    is not re-walked on every open).
  - NukePlugin.invalidate_cache still clears everything.
"""

import importlib.util
import os
import sys
import types
from unittest.mock import MagicMock


class _FakeMenuItem:
    """Leaf menu item: only .name() is read by _menu_fingerprint."""

    def __init__(self, name):
        self._name = name

    def name(self):
        return self._name


class _FakeMenu(_FakeMenuItem):
    """Submenu: exposes .items(). Subclasses _FakeMenuItem so leaves are
    not instances of the Menu type (matching Nuke's class hierarchy as
    far as the isinstance check in _menu_fingerprint cares)."""

    def __init__(self, name, children):
        super().__init__(name)
        self._children = children

    def items(self):
        return self._children


def _build_pyside_stubs():
    pyside6 = types.ModuleType("PySide6")
    qtcore = types.ModuleType("PySide6.QtCore")
    qtgui = types.ModuleType("PySide6.QtGui")
    qtwidgets = types.ModuleType("PySide6.QtWidgets")

    qtcore.Qt = MagicMock()
    qtcore.QEvent = MagicMock()
    qtcore.QAbstractListModel = type("QAbstractListModel", (), {
        "__init__": lambda self, *a, **k: None,
        "modelReset": MagicMock(),
    })
    qtcore.QModelIndex = MagicMock
    qtcore.QSize = MagicMock
    qtcore.QRect = MagicMock
    qtcore.Signal = MagicMock(return_value=MagicMock())
    qtcore.QTimer = type(
        "QTimer", (), {"singleShot": staticmethod(lambda delay_ms, cb: None)}
    )

    qtgui.QCursor = MagicMock()
    qtgui.QIcon = MagicMock
    qtgui.QColor = MagicMock
    qtgui.QBrush = MagicMock
    qtgui.QPen = MagicMock

    qtwidgets.QDialog = type("QDialog", (), {"__init__": lambda self, *a, **k: None})
    qtwidgets.QLineEdit = type("QLineEdit", (), {"__init__": lambda self, *a, **k: None})
    qtwidgets.QListView = type("QListView", (), {"__init__": lambda self, *a, **k: None})
    qtwidgets.QVBoxLayout = type("QVBoxLayout", (), {"__init__": lambda self, *a, **k: None})
    qtwidgets.QStyledItemDelegate = type("QStyledItemDelegate", (), {"__init__": lambda self, *a, **k: None})
    qtwidgets.QStyle = MagicMock()
    qtwidgets.QMainWindow = type("QMainWindow", (), {"__init__": lambda self, *a, **k: None})
    qtwidgets.QApplication = type(
        "QApplication", (), {"instance": staticmethod(lambda: MagicMock())}
    )

    pyside6.QtCore = qtcore
    pyside6.QtGui = qtgui
    pyside6.QtWidgets = qtwidgets
    return pyside6


def _build_nuke_stub():
    nuke = types.ModuleType("nuke")
    nuke.Menu = _FakeMenu
    nuke.MenuItem = _FakeMenuItem
    nuke.NUKE_VERSION_MAJOR = 15
    nuke.menu = lambda name: None
    nuke.defaultNodeColor = lambda cls: 0
    nuke.pluginPath = lambda: []
    return nuke


def _load_nuke_plugin():
    """Load tabtabtab_nuke under a fresh test-name spec with nuke + PySide
    stubbed for the duration of the import only."""
    pyside6 = _build_pyside_stubs()
    nuke_stub = _build_nuke_stub()

    stub_modules = {
        "PySide6": pyside6,
        "PySide6.QtCore": pyside6.QtCore,
        "PySide6.QtGui": pyside6.QtGui,
        "PySide6.QtWidgets": pyside6.QtWidgets,
        "nuke": nuke_stub,
    }
    previous = {name: sys.modules.get(name) for name in stub_modules}

    sys.modules.update(stub_modules)
    sys.modules.setdefault("PySide2", types.ModuleType("PySide2"))
    # tabtabtab_nuke does `from tabtabtab_nuke_core import ...`; make sure a
    # stale copy from another test's stubbed import isn't reused.
    sys.modules.pop("tabtabtab_nuke_core", None)

    repo_root = os.path.join(os.path.dirname(__file__), "..")
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)

    plugin_path = os.path.join(repo_root, "tabtabtab_nuke.py")
    spec = importlib.util.spec_from_file_location(
        "tabtabtab_nuke_fingerprint_test", plugin_path
    )
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    finally:
        for name, prev in previous.items():
            if prev is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = prev
        sys.modules.pop("tabtabtab_nuke_core", None)
    return module


# --- tests --------------------------------------------------------------


def _deep_tree(leaf_name):
    """Three levels deep: Root > Mid > Inner > <leaf_name>. The leaf sits
    below the old depth-2 fingerprint bound."""
    return _FakeMenu("Root", [
        _FakeMenu("Mid", [
            _FakeMenu("Inner", [
                _FakeMenuItem(leaf_name),
            ]),
        ]),
    ])


def test_fingerprint_detects_deep_change():
    module = _load_nuke_plugin()

    fp_before = module._menu_fingerprint(_deep_tree("Blur"))
    fp_after = module._menu_fingerprint(_deep_tree("Defocus"))

    assert fp_before is not None
    assert fp_before != fp_after


def test_fingerprint_stable_for_identical_trees():
    module = _load_nuke_plugin()

    assert (
        module._menu_fingerprint(_deep_tree("Blur"))
        == module._menu_fingerprint(_deep_tree("Blur"))
    )


def test_invalidate_color_cache_keeps_item_cache():
    module = _load_nuke_plugin()
    plugin = module.NukePlugin()

    plugin._cached_items = [{"menupath": "Cat/Node"}]
    plugin._cached_menu_fingerprint = ("fp",)
    plugin._color_cache = {"Blur": ("c", "c")}

    plugin.invalidate_color_cache()

    assert plugin._color_cache == {}
    assert plugin._cached_items == [{"menupath": "Cat/Node"}]
    assert plugin._cached_menu_fingerprint == ("fp",)


def test_invalidate_cache_clears_everything():
    module = _load_nuke_plugin()
    plugin = module.NukePlugin()

    plugin._cached_items = [{"menupath": "Cat/Node"}]
    plugin._cached_menu_fingerprint = ("fp",)
    plugin._color_cache = {"Blur": ("c", "c")}

    plugin.invalidate_cache()

    assert plugin._color_cache == {}
    assert plugin._cached_items is None
    assert plugin._cached_menu_fingerprint is None
