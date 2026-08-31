"""Regression test for issue #16: cursor stuck on the text-editing (IBeam)
shape after the popup closes.

TabTabTabWidget.under_cursor() always positions the popup so the mouse
pointer lands directly over the QLineEdit input, which shows an IBeam
cursor while hovered. The popup is a frameless top-level window that gets
hidden (not destroyed) on every close path, and typically closes without
the pointer moving off it — a race that can leave the IBeam cursor
displayed on screen after the popup disappears.

TabTabTabWidget.close() works around this by explicitly forcing the
cursor back to the arrow shape via an override cursor, restored on the
next event-loop tick. This test verifies that push/restore pairing
happens on every close(), independent of real Qt.
"""

import importlib.util
import os
import sys
import types
from unittest.mock import MagicMock


def _load_tabtabtab_module_with_stubs():
    """Load tabtabtab_nuke_core with minimal PySide6 stubs injected so no
    real Qt is required. Returns (module, qtwidgets_stub, qtcore_stub) so
    the caller can inspect QApplication / QTimer.singleShot calls.
    """
    pyside6_stub = types.ModuleType("PySide6")
    qtcore_stub = types.ModuleType("PySide6.QtCore")
    qtgui_stub = types.ModuleType("PySide6.QtGui")
    qtwidgets_stub = types.ModuleType("PySide6.QtWidgets")

    # QtCore stubs
    qtcore_stub.Qt = MagicMock()
    qtcore_stub.QEvent = MagicMock()
    qtcore_stub.QAbstractListModel = type("QAbstractListModel", (), {
        "__init__": lambda self, *args, **kwargs: None,
        "modelReset": MagicMock(),
    })
    qtcore_stub.QModelIndex = MagicMock
    qtcore_stub.QSize = MagicMock
    qtcore_stub.QRect = MagicMock
    qtcore_stub.Signal = MagicMock(return_value=MagicMock())
    qtcore_stub.QTimer = MagicMock()
    qtcore_stub.QTimer.singleShot = MagicMock()

    # QtGui stubs
    qtgui_stub.QCursor = MagicMock()
    qtgui_stub.QIcon = MagicMock
    qtgui_stub.QColor = MagicMock
    qtgui_stub.QBrush = MagicMock
    qtgui_stub.QPen = MagicMock

    # QtWidgets stubs
    qtwidgets_stub.QApplication = MagicMock()
    qtwidgets_stub.QApplication.setOverrideCursor = MagicMock()
    qtwidgets_stub.QApplication.restoreOverrideCursor = MagicMock()

    # QDialog needs a real (no-op) close() so TabTabTabWidget.close()'s
    # super().close() call has something to resolve to.
    qtwidgets_stub.QDialog = type("QDialog", (), {
        "__init__": lambda self, *args, **kwargs: None,
        "close": lambda self: None,
    })
    qtwidgets_stub.QLineEdit = type("QLineEdit", (), {"__init__": lambda self, *args, **kwargs: None})
    qtwidgets_stub.QListView = type("QListView", (), {"__init__": lambda self, *args, **kwargs: None})
    qtwidgets_stub.QVBoxLayout = type("QVBoxLayout", (), {"__init__": lambda self, *args, **kwargs: None})
    qtwidgets_stub.QStyledItemDelegate = type("QStyledItemDelegate", (), {"__init__": lambda self, *args, **kwargs: None})
    qtwidgets_stub.QStyle = MagicMock()

    pyside6_stub.QtCore = qtcore_stub
    pyside6_stub.QtGui = qtgui_stub
    pyside6_stub.QtWidgets = qtwidgets_stub

    stub_module_names = ["PySide6", "PySide6.QtCore", "PySide6.QtGui", "PySide6.QtWidgets"]
    previous_modules = {name: sys.modules.get(name) for name in stub_module_names}

    sys.modules["PySide6"] = pyside6_stub
    sys.modules["PySide6.QtCore"] = qtcore_stub
    sys.modules["PySide6.QtGui"] = qtgui_stub
    sys.modules["PySide6.QtWidgets"] = qtwidgets_stub

    pyside2_stub = types.ModuleType("PySide2")
    sys.modules.setdefault("PySide2", pyside2_stub)

    core_module_path = os.path.join(os.path.dirname(__file__), "..", "tabtabtab_nuke_core.py")
    spec = importlib.util.spec_from_file_location("tabtabtab_core_under_test_close", core_module_path)
    module = importlib.util.module_from_spec(spec)

    try:
        spec.loader.exec_module(module)
    finally:
        for name in stub_module_names:
            if previous_modules[name] is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous_modules[name]

    return module, qtwidgets_stub, qtcore_stub


def test_close_forces_arrow_cursor_and_schedules_restore():
    """close() must push an arrow-cursor override immediately (so the
    IBeam left by the hovered QLineEdit doesn't linger) and schedule
    restoreOverrideCursor() so the override doesn't stick around forever.
    """
    module, qtwidgets_stub, qtcore_stub = _load_tabtabtab_module_with_stubs()

    # Build a bare instance without running the full __init__ (which
    # constructs a real widget tree we don't need for this test).
    widget = object.__new__(module.TabTabTabWidget)
    widget.weights = MagicMock()

    widget.close()

    # Weights are still saved on close.
    widget.weights.save.assert_called_once()

    # An arrow-cursor override is pushed immediately, before the widget
    # is actually hidden, guaranteeing an on-screen cursor update.
    qtwidgets_stub.QApplication.setOverrideCursor.assert_called_once_with(
        module.Qt.ArrowCursor
    )

    # The override is scheduled to be restored on the next event-loop
    # tick, not left pushed forever.
    qtcore_stub.QTimer.singleShot.assert_called_once()
    delay, restore_fn = qtcore_stub.QTimer.singleShot.call_args[0]
    assert delay == 0
    assert restore_fn == qtwidgets_stub.QApplication.restoreOverrideCursor


def test_close_pairs_override_push_with_restore_across_repeated_opens():
    """Repeated close() calls (Escape, click-outside, node creation can
    all fire close() in the same session as the popup is reused) must
    each push exactly one override and schedule exactly one restore, so
    the override-cursor stack never grows unbounded.
    """
    module, qtwidgets_stub, qtcore_stub = _load_tabtabtab_module_with_stubs()

    widget = object.__new__(module.TabTabTabWidget)
    widget.weights = MagicMock()

    for _ in range(3):
        widget.close()

    assert qtwidgets_stub.QApplication.setOverrideCursor.call_count == 3
    assert qtcore_stub.QTimer.singleShot.call_count == 3
