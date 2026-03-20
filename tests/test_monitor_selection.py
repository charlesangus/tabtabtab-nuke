"""Tests for monitor selection logic in TabTabTabWidget.under_cursor().

Verifies that the palette opens on whichever monitor the cursor is on,
using QApplication.screenAt() with fallback to self.screen().
"""

import importlib.util
import os
import sys
import types
from unittest.mock import MagicMock


def _make_mock_screen(left, top, width, height):
    """Create a mock QScreen with the given geometry."""
    screen = MagicMock()
    geometry = MagicMock()
    geometry.left.return_value = left
    geometry.top.return_value = top
    geometry.right.return_value = left + width
    geometry.bottom.return_value = top + height
    geometry.width.return_value = width
    geometry.height.return_value = height
    screen.geometry.return_value = geometry
    return screen


def _load_tabtabtab_module_with_stubs(cursor_x, cursor_y, screen_at_fn, fallback_screen):
    """Load tabtabtab module with PySide stubs injected so no real Qt is required.

    Returns the loaded module object. The caller should bind under_cursor to a
    mock widget and call it to exercise the monitor selection logic.

    Args:
        cursor_x: Simulated cursor X position.
        cursor_y: Simulated cursor Y position.
        screen_at_fn: Callable to use as QApplication.screenAt, or None to simulate
            the method being absent (tests the fallback path).
        fallback_screen: Mock screen returned by self.screen() when screenAt unavailable.

    Returns:
        Tuple of (loaded module, QCursor pos mock) so tests can verify cursor position.
    """
    # Build minimal PySide6 stub tree
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

    # QtGui stubs
    cursor_position_mock = MagicMock()
    cursor_position_mock.x.return_value = cursor_x
    cursor_position_mock.y.return_value = cursor_y

    cursor_instance_mock = MagicMock()
    cursor_instance_mock.pos.return_value = cursor_position_mock

    qtgui_stub.QCursor = MagicMock(return_value=cursor_instance_mock)
    qtgui_stub.QIcon = MagicMock
    qtgui_stub.QColor = MagicMock
    qtgui_stub.QBrush = MagicMock
    qtgui_stub.QPen = MagicMock

    # QtWidgets stubs — QApplication class controls screenAt availability
    if screen_at_fn is not None:
        # screenAt is available: use a class that has it as a static/class method
        class _QApplicationWithScreenAt:
            @staticmethod
            def screenAt(pos):
                return screen_at_fn(pos)

        qtwidgets_stub.QApplication = _QApplicationWithScreenAt
    else:
        # screenAt is absent: use a class that does NOT have screenAt
        class _QApplicationWithoutScreenAt:
            pass

        qtwidgets_stub.QApplication = _QApplicationWithoutScreenAt

    # Other widget stubs needed for module import
    qtwidgets_stub.QDialog = type("QDialog", (), {"__init__": lambda self, *args, **kwargs: None})
    qtwidgets_stub.QLineEdit = type("QLineEdit", (), {"__init__": lambda self, *args, **kwargs: None})
    qtwidgets_stub.QListView = type("QListView", (), {"__init__": lambda self, *args, **kwargs: None})
    qtwidgets_stub.QVBoxLayout = type("QVBoxLayout", (), {"__init__": lambda self, *args, **kwargs: None})
    qtwidgets_stub.QStyledItemDelegate = type("QStyledItemDelegate", (), {"__init__": lambda self, *args, **kwargs: None})
    qtwidgets_stub.QStyle = MagicMock()

    pyside6_stub.QtCore = qtcore_stub
    pyside6_stub.QtGui = qtgui_stub
    pyside6_stub.QtWidgets = qtwidgets_stub

    # Temporarily inject stubs into sys.modules, preserving any existing entries
    stub_module_names = ["PySide6", "PySide6.QtCore", "PySide6.QtGui", "PySide6.QtWidgets"]
    previous_modules = {name: sys.modules.get(name) for name in stub_module_names}

    sys.modules["PySide6"] = pyside6_stub
    sys.modules["PySide6.QtCore"] = qtcore_stub
    sys.modules["PySide6.QtGui"] = qtgui_stub
    sys.modules["PySide6.QtWidgets"] = qtwidgets_stub

    # Also stub PySide2 so the ImportError fallback doesn't get picked up
    pyside2_stub = types.ModuleType("PySide2")
    sys.modules.setdefault("PySide2", pyside2_stub)

    core_module_path = os.path.join(os.path.dirname(__file__), "..", "tabtabtab_nuke_core.py")
    spec = importlib.util.spec_from_file_location("tabtabtab_core_under_test", core_module_path)
    module = importlib.util.module_from_spec(spec)

    try:
        spec.loader.exec_module(module)
    finally:
        # Restore sys.modules to previous state
        for name in stub_module_names:
            if previous_modules[name] is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous_modules[name]

    return module, cursor_position_mock


def _call_under_cursor(cursor_x, cursor_y, widget_width, widget_height, screen_at_fn, fallback_screen):
    """Run under_cursor() on a mock widget and return the widget so move() args can be inspected.

    Args:
        cursor_x: Simulated cursor X position.
        cursor_y: Simulated cursor Y position.
        widget_width: Simulated widget width.
        widget_height: Simulated widget height.
        screen_at_fn: Callable for QApplication.screenAt, or None to test fallback.
        fallback_screen: Mock screen returned by self.screen() as fallback.

    Returns:
        MagicMock widget with move() call recorded.
    """
    module, _cursor_pos = _load_tabtabtab_module_with_stubs(
        cursor_x, cursor_y, screen_at_fn, fallback_screen
    )

    mock_widget = MagicMock()
    mock_widget.width.return_value = widget_width
    mock_widget.height.return_value = widget_height
    mock_widget.screen.return_value = fallback_screen

    real_under_cursor = module.TabTabTabWidget.under_cursor
    real_under_cursor(mock_widget)

    return mock_widget


# Two-monitor layout: left monitor 0,0 1920x1080; right monitor 1920,0 1920x1080
LEFT_MONITOR = _make_mock_screen(left=0, top=0, width=1920, height=1080)
RIGHT_MONITOR = _make_mock_screen(left=1920, top=0, width=1920, height=1080)

WIDGET_WIDTH = 400
WIDGET_HEIGHT = 600


def test_cursor_on_right_monitor_opens_palette_on_right():
    """When cursor is on the right monitor, palette should open there (x >= 1920)."""
    cursor_x = 2500
    cursor_y = 500

    def screen_at_for_dual_monitor(pos):
        if pos.x() >= 1920:
            return RIGHT_MONITOR
        return LEFT_MONITOR

    widget = _call_under_cursor(
        cursor_x=cursor_x,
        cursor_y=cursor_y,
        widget_width=WIDGET_WIDTH,
        widget_height=WIDGET_HEIGHT,
        screen_at_fn=screen_at_for_dual_monitor,
        fallback_screen=LEFT_MONITOR,
    )

    widget.move.assert_called_once()
    move_x, move_y = widget.move.call_args[0]
    assert move_x >= 1920, (
        f"Expected palette on right monitor (x >= 1920), got x={move_x}"
    )
    assert move_x < 1920 + 1920, (
        f"Expected palette within right monitor bounds (x < 3840), got x={move_x}"
    )


def test_cursor_on_left_monitor_opens_palette_on_left():
    """When cursor is on the left monitor, palette should open there (x < 1920)."""
    cursor_x = 500
    cursor_y = 500

    def screen_at_for_dual_monitor(pos):
        if pos.x() >= 1920:
            return RIGHT_MONITOR
        return LEFT_MONITOR

    widget = _call_under_cursor(
        cursor_x=cursor_x,
        cursor_y=cursor_y,
        widget_width=WIDGET_WIDTH,
        widget_height=WIDGET_HEIGHT,
        screen_at_fn=screen_at_for_dual_monitor,
        fallback_screen=LEFT_MONITOR,
    )

    widget.move.assert_called_once()
    move_x, move_y = widget.move.call_args[0]
    assert move_x >= 0, (
        f"Expected palette on left monitor (x >= 0), got x={move_x}"
    )
    assert move_x < 1920, (
        f"Expected palette on left monitor (x < 1920), got x={move_x}"
    )


def test_screenat_fallback_when_unavailable():
    """When screenAt() is not available, fall back to self.screen() without crash."""
    cursor_x = 500
    cursor_y = 500

    widget = _call_under_cursor(
        cursor_x=cursor_x,
        cursor_y=cursor_y,
        widget_width=WIDGET_WIDTH,
        widget_height=WIDGET_HEIGHT,
        screen_at_fn=None,  # screenAt absent — triggers fallback path
        fallback_screen=LEFT_MONITOR,
    )

    # Should still call move() using the fallback screen geometry
    widget.move.assert_called_once()
    move_x, move_y = widget.move.call_args[0]
    # Fallback is LEFT_MONITOR (0..1920), so x should be in left monitor range
    assert move_x >= 0, f"Expected valid x position >= 0, got x={move_x}"
    assert move_x < 1920, f"Expected palette on fallback left monitor (x < 1920), got x={move_x}"
