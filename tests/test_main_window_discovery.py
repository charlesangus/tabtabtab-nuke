"""Tests for Nuke main window discovery and the parent re-attachment path
used by preload() to recover from preload-before-main-window timing.

Covers:
  - _find_nuke_main_window() classname-match priority over other QMainWindows
  - _find_nuke_main_window() title fallback for parentless windows
  - _find_nuke_main_window() returning None when neither check matches
  - _try_reparent_preloaded() parenting when the main window is available
  - _try_reparent_preloaded() scheduling a retry when the main window is absent
  - _try_reparent_preloaded() bailing out when the widget is already parented or visible
"""

import importlib.util
import os
import sys
import types
from unittest.mock import MagicMock


_NUKE_DOCK_CLASSNAME = "Foundry::UI::DockMainWindow"


def _build_pyside_stubs(top_level_widgets_holder, scheduled_calls):
    """Construct PySide6 stub modules with QApplication.instance() reading
    from the mutable `top_level_widgets_holder` list and QTimer.singleShot
    appending (delay_ms, callback) tuples to `scheduled_calls`.

    The two outparams give tests a hook to mutate the topLevelWidgets list
    after import (to simulate Nuke's main window appearing later) and to
    drive scheduled retries deterministically without a real event loop.
    """
    pyside6 = types.ModuleType("PySide6")
    qtcore = types.ModuleType("PySide6.QtCore")
    qtgui = types.ModuleType("PySide6.QtGui")
    qtwidgets = types.ModuleType("PySide6.QtWidgets")

    qtcore.Qt = MagicMock()
    qtcore.QEvent = MagicMock()
    qtcore.QAbstractListModel = type("QAbstractListModel", (), {
        "__init__": lambda self, *args, **kwargs: None,
        "modelReset": MagicMock(),
    })
    qtcore.QModelIndex = MagicMock
    qtcore.QSize = MagicMock
    qtcore.QRect = MagicMock
    qtcore.Signal = MagicMock(return_value=MagicMock())

    class _StubQTimer:
        @staticmethod
        def singleShot(delay_ms, callback):
            scheduled_calls.append((delay_ms, callback))

    qtcore.QTimer = _StubQTimer

    qtgui.QCursor = MagicMock()
    qtgui.QIcon = MagicMock
    qtgui.QColor = MagicMock
    qtgui.QBrush = MagicMock
    qtgui.QPen = MagicMock

    qtwidgets.QDialog = type("QDialog", (), {"__init__": lambda self, *args, **kwargs: None})
    qtwidgets.QLineEdit = type("QLineEdit", (), {"__init__": lambda self, *args, **kwargs: None})
    qtwidgets.QListView = type("QListView", (), {"__init__": lambda self, *args, **kwargs: None})
    qtwidgets.QVBoxLayout = type("QVBoxLayout", (), {"__init__": lambda self, *args, **kwargs: None})
    qtwidgets.QStyledItemDelegate = type("QStyledItemDelegate", (), {"__init__": lambda self, *args, **kwargs: None})
    qtwidgets.QStyle = MagicMock()
    qtwidgets.QMainWindow = type("QMainWindow", (), {
        "__init__": lambda self, *args, **kwargs: None,
    })

    class _StubQApplication:
        @staticmethod
        def instance():
            app_mock = MagicMock()
            app_mock.topLevelWidgets.return_value = list(top_level_widgets_holder)
            return app_mock

    qtwidgets.QApplication = _StubQApplication

    pyside6.QtCore = qtcore
    pyside6.QtGui = qtgui
    pyside6.QtWidgets = qtwidgets

    return pyside6, qtcore, qtgui, qtwidgets


def _load_module(top_level_widgets_holder, scheduled_calls):
    """Load tabtabtab_nuke_core with stubs wired to the given holders.

    Returns (module, QMainWindowStub). Tests subclass the QMainWindow stub
    to build fixtures that satisfy isinstance checks.
    """
    pyside6, qtcore, qtgui, qtwidgets = _build_pyside_stubs(
        top_level_widgets_holder, scheduled_calls
    )

    stub_names = ["PySide6", "PySide6.QtCore", "PySide6.QtGui", "PySide6.QtWidgets"]
    previous = {name: sys.modules.get(name) for name in stub_names}

    sys.modules["PySide6"] = pyside6
    sys.modules["PySide6.QtCore"] = qtcore
    sys.modules["PySide6.QtGui"] = qtgui
    sys.modules["PySide6.QtWidgets"] = qtwidgets

    pyside2_stub = types.ModuleType("PySide2")
    sys.modules.setdefault("PySide2", pyside2_stub)

    core_path = os.path.join(os.path.dirname(__file__), "..", "tabtabtab_nuke_core.py")
    spec = importlib.util.spec_from_file_location(
        "tabtabtab_core_main_window_discovery_test", core_path
    )
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    finally:
        for name in stub_names:
            if previous[name] is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous[name]

    return module, qtwidgets.QMainWindow


def _make_mock_main_window(qmainwindow_class, classname="", parent_widget=None, title=""):
    """Build a QMainWindow-subclass instance with controllable probe methods.

    Subclassing the stub's QMainWindow is required so isinstance() checks
    in _find_nuke_main_window() succeed; methods are attached per-instance
    so each fixture can return its own classname/parent/title.
    """
    instance = qmainwindow_class.__new__(qmainwindow_class)
    instance._classname = classname
    instance._parent_widget = parent_widget
    instance._title = title

    def metaObject():
        meta = MagicMock()
        meta.className.return_value = instance._classname
        return meta

    instance.metaObject = metaObject
    instance.parent = lambda: instance._parent_widget
    instance.windowTitle = lambda: instance._title
    return instance


# --- _find_nuke_main_window tests ---------------------------------------


def test_find_main_window_picks_classname_match_over_other_qmainwindows():
    """The dock main window must win even when other QMainWindows are
    present in arbitrary order (floating panels, Hiero/Studio bins, etc.).
    """
    top_level = []
    scheduled = []
    module, QMainWindow = _load_module(top_level, scheduled)

    floating_panel = _make_mock_main_window(
        QMainWindow, classname="QMainWindow", title="Some Floating Panel"
    )
    dock_main = _make_mock_main_window(
        QMainWindow, classname=_NUKE_DOCK_CLASSNAME, title="script.nk - NukeX 14.0v5"
    )
    other_panel = _make_mock_main_window(
        QMainWindow, classname="QMainWindow", title="Another Panel"
    )

    # Place dock main between two non-matching QMainWindows; classname check
    # must select dock_main regardless of position.
    top_level.extend([floating_panel, dock_main, other_panel])

    assert module._find_nuke_main_window() is dock_main


def test_find_main_window_falls_back_to_title_match_for_parentless_window():
    """If no widget matches the classname, the parentless title-match
    fallback should kick in for the canonical Nuke title shape.
    """
    top_level = []
    scheduled = []
    module, QMainWindow = _load_module(top_level, scheduled)

    nuke_main = _make_mock_main_window(
        QMainWindow, classname="QMainWindow", title="script.nk - Nuke 14.0v5"
    )
    top_level.append(nuke_main)

    assert module._find_nuke_main_window() is nuke_main


def test_find_main_window_title_fallback_excludes_parented_panels():
    """A QMainWindow whose title contains ' - Nuke' but which has a parent
    is presumably an embedded panel; the fallback must skip it.
    """
    top_level = []
    scheduled = []
    module, QMainWindow = _load_module(top_level, scheduled)

    parent_widget_marker = MagicMock()
    parented_panel = _make_mock_main_window(
        QMainWindow,
        classname="QMainWindow",
        parent_widget=parent_widget_marker,
        title="something - Nuke 14.0v5",
    )
    top_level.append(parented_panel)

    assert module._find_nuke_main_window() is None


def test_find_main_window_returns_none_when_nothing_matches():
    """No classname match and no title-bearing parentless QMainWindow ->
    return None rather than fall back to grabbing an arbitrary panel.
    """
    top_level = []
    scheduled = []
    module, QMainWindow = _load_module(top_level, scheduled)

    arbitrary_panel = _make_mock_main_window(
        QMainWindow, classname="QMainWindow", title="just a panel"
    )
    top_level.append(arbitrary_panel)

    assert module._find_nuke_main_window() is None


def test_find_main_window_classname_match_recognised_via_metaobject():
    """Title shape doesn't matter when the classname matches — covers the
    case where a script hasn't been opened yet (default Nuke title).
    """
    top_level = []
    scheduled = []
    module, QMainWindow = _load_module(top_level, scheduled)

    dock_main = _make_mock_main_window(
        QMainWindow, classname=_NUKE_DOCK_CLASSNAME, title=""
    )
    top_level.append(dock_main)

    assert module._find_nuke_main_window() is dock_main


# --- _try_reparent_preloaded tests --------------------------------------


def _make_preload_widget(currently_parented=False, currently_visible=False):
    """Build a widget mock that records setParent calls and exposes
    parent()/isVisible() probes the helper checks before re-parenting.
    """
    widget = MagicMock()
    widget.parent.return_value = MagicMock() if currently_parented else None
    widget.isVisible.return_value = currently_visible
    return widget


def test_try_reparent_parents_widget_when_main_window_available():
    """Happy path: parentless widget + main window in topLevelWidgets()
    -> setParent called with the main window and the right window flags.
    """
    top_level = []
    scheduled = []
    module, QMainWindow = _load_module(top_level, scheduled)

    dock_main = _make_mock_main_window(
        QMainWindow, classname=_NUKE_DOCK_CLASSNAME
    )
    top_level.append(dock_main)

    widget = _make_preload_widget()

    module._try_reparent_preloaded(widget, attempts_remaining=5)

    widget.setParent.assert_called_once()
    parent_arg, flags_arg = widget.setParent.call_args[0]
    assert parent_arg is dock_main
    # Flags arg should be the OR of Qt.Dialog and Qt.FramelessWindowHint —
    # we don't try to introspect MagicMock OR results, but we do require
    # that setParent received two positional args (parent + flags) so a
    # bare setParent(parent) call (which would demote to a child) doesn't
    # silently slip through.
    assert flags_arg is not None
    assert not scheduled, "should not schedule retry once parented"


def test_try_reparent_schedules_retry_when_main_window_absent():
    """No main window present -> setParent not called, retry scheduled."""
    top_level = []
    scheduled = []
    module, QMainWindow = _load_module(top_level, scheduled)

    widget = _make_preload_widget()

    module._try_reparent_preloaded(widget, attempts_remaining=5)

    widget.setParent.assert_not_called()
    assert len(scheduled) == 1
    delay_ms, callback = scheduled[0]
    assert delay_ms == module._REPARENT_RETRY_INTERVAL_MS
    assert callable(callback)


def test_try_reparent_eventually_succeeds_when_main_window_appears():
    """Realistic preload race: first attempt finds nothing, main window
    appears between retries, next retry parents the widget.
    """
    top_level = []
    scheduled = []
    module, QMainWindow = _load_module(top_level, scheduled)

    widget = _make_preload_widget()

    # First attempt: no main window yet.
    module._try_reparent_preloaded(widget, attempts_remaining=5)
    widget.setParent.assert_not_called()
    assert len(scheduled) == 1

    # Main window appears.
    dock_main = _make_mock_main_window(
        QMainWindow, classname=_NUKE_DOCK_CLASSNAME
    )
    top_level.append(dock_main)

    # Drive the scheduled retry callback.
    _delay, retry_callback = scheduled[0]
    scheduled.clear()
    retry_callback()

    widget.setParent.assert_called_once()
    parent_arg = widget.setParent.call_args[0][0]
    assert parent_arg is dock_main
    assert not scheduled, "should not schedule another retry once parented"


def test_try_reparent_stops_after_max_attempts():
    """Attempt budget exhaustion -> no further retry scheduled."""
    top_level = []
    scheduled = []
    module, QMainWindow = _load_module(top_level, scheduled)

    widget = _make_preload_widget()
    module._try_reparent_preloaded(widget, attempts_remaining=1)

    widget.setParent.assert_not_called()
    assert scheduled == [], "last attempt must not enqueue another retry"


def test_try_reparent_skips_when_widget_already_parented():
    """If launch()'s recovery path beat us to it, the helper must do
    nothing — no setParent, no retry.
    """
    top_level = []
    scheduled = []
    module, QMainWindow = _load_module(top_level, scheduled)

    dock_main = _make_mock_main_window(
        QMainWindow, classname=_NUKE_DOCK_CLASSNAME
    )
    top_level.append(dock_main)

    widget = _make_preload_widget(currently_parented=True)
    module._try_reparent_preloaded(widget, attempts_remaining=5)

    widget.setParent.assert_not_called()
    assert scheduled == []


def test_try_reparent_skips_when_widget_visible():
    """If the user opened the popup before the retry fired, leave it
    alone — re-parenting a visible widget would disrupt the open dialog
    and launch() owns recovery from this point on.
    """
    top_level = []
    scheduled = []
    module, QMainWindow = _load_module(top_level, scheduled)

    dock_main = _make_mock_main_window(
        QMainWindow, classname=_NUKE_DOCK_CLASSNAME
    )
    top_level.append(dock_main)

    widget = _make_preload_widget(currently_visible=True)
    module._try_reparent_preloaded(widget, attempts_remaining=5)

    widget.setParent.assert_not_called()
    assert scheduled == []


def test_try_reparent_skips_when_widget_destroyed():
    """If the underlying C++ widget has been destroyed, parent() raises
    RuntimeError; the helper must swallow it and stop retrying.
    """
    top_level = []
    scheduled = []
    module, QMainWindow = _load_module(top_level, scheduled)

    widget = MagicMock()
    widget.parent.side_effect = RuntimeError("wrapped C++ object destroyed")

    module._try_reparent_preloaded(widget, attempts_remaining=5)

    widget.setParent.assert_not_called()
    assert scheduled == []
