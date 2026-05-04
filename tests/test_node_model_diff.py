"""Tests for NodeModel._apply_items incremental diff.

Verifies that the diff emits the minimum set of row operations to morph
one visible item set into another, instead of falling back to modelReset.
This is what keeps the popup's selection stable across the deferred
fresh-refresh tick on show() and avoids visible flicker.

Covers:
  - No-op when before/after lists match → zero row operations.
  - Pure insertion into an empty model → ordered beginInsertRows.
  - Pure removal → back-to-front beginRemoveRows so indices stay valid.
  - Reorder of identical items → beginMoveRows, no inserts or removes.
  - In-place score change → dataChanged only, no structural ops.
  - Visually-identical refresh → no dataChanged emitted (quiet refresh).
  - Mixed remove/insert/reorder → removes precede inserts and moves.
  - num_items cap → off-window churn is silent; off-window items
    promoted into the visible window do surface as inserts.
"""

import importlib.util
import os
import sys
import types
from unittest.mock import MagicMock


class _StubIndex:
    """Stand-in for QModelIndex; only .row() is exercised."""

    def __init__(self, row=-1):
        self._row = row

    def row(self):
        return self._row


class _RecordingDataChanged:
    """Stand-in for the QAbstractListModel.dataChanged signal that
    appends each emit to the owning model's recorded_ops list."""

    def __init__(self, owner):
        self._owner = owner

    def emit(self, top, bottom):
        self._owner.recorded_ops.append(("data_changed", top.row(), bottom.row()))


class _StubAbstractListModel:
    """QAbstractListModel stand-in that records every row operation in
    order to self.recorded_ops, so tests can assert on the exact diff."""

    # Class-level attribute referenced elsewhere in the module body; not
    # used by _apply_items but must exist so import doesn't blow up.
    modelReset = MagicMock()

    def __init__(self, *args, **kwargs):
        self.recorded_ops = []
        self.dataChanged = _RecordingDataChanged(self)

    def beginRemoveRows(self, parent, first, last):
        self.recorded_ops.append(("begin_remove", first, last))

    def endRemoveRows(self):
        self.recorded_ops.append(("end_remove",))

    def beginInsertRows(self, parent, first, last):
        self.recorded_ops.append(("begin_insert", first, last))

    def endInsertRows(self):
        self.recorded_ops.append(("end_insert",))

    def beginMoveRows(self, source_parent, source_first, source_last,
                      dest_parent, dest_child):
        self.recorded_ops.append(
            ("begin_move", source_first, source_last, dest_child)
        )
        return True

    def endMoveRows(self):
        self.recorded_ops.append(("end_move",))

    def index(self, row, column=0, parent=None):
        return _StubIndex(row)


def _build_pyside_stubs():
    """Construct PySide6 stub modules wired to the recording
    QAbstractListModel above."""
    pyside6 = types.ModuleType("PySide6")
    qtcore = types.ModuleType("PySide6.QtCore")
    qtgui = types.ModuleType("PySide6.QtGui")
    qtwidgets = types.ModuleType("PySide6.QtWidgets")

    qtcore.Qt = MagicMock()
    qtcore.QEvent = MagicMock()
    qtcore.QAbstractListModel = _StubAbstractListModel
    qtcore.QModelIndex = lambda: _StubIndex(-1)
    qtcore.QSize = MagicMock
    qtcore.QRect = MagicMock
    qtcore.Signal = MagicMock(return_value=MagicMock())
    qtcore.QTimer = type(
        "QTimer", (), {"singleShot": staticmethod(lambda delay_ms, callback: None)}
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
    return pyside6, qtcore, qtgui, qtwidgets


def _load_core():
    """Load tabtabtab_nuke_core under a fresh test-name spec, with stubs
    swapped into sys.modules for the duration of the import only."""
    pyside6, qtcore, qtgui, qtwidgets = _build_pyside_stubs()
    stub_names = ["PySide6", "PySide6.QtCore", "PySide6.QtGui", "PySide6.QtWidgets"]
    previous = {name: sys.modules.get(name) for name in stub_names}

    sys.modules["PySide6"] = pyside6
    sys.modules["PySide6.QtCore"] = qtcore
    sys.modules["PySide6.QtGui"] = qtgui
    sys.modules["PySide6.QtWidgets"] = qtwidgets
    sys.modules.setdefault("PySide2", types.ModuleType("PySide2"))

    core_path = os.path.join(os.path.dirname(__file__), "..", "tabtabtab_nuke_core.py")
    spec = importlib.util.spec_from_file_location(
        "tabtabtab_core_node_model_diff_test", core_path
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
    return module


def _make_model(module, num_items=18, items=None):
    """Construct a NodeModel without running its __init__ (which would
    require a plugin and call update()). We only need the recording
    base-class state plus the two fields _apply_items reads."""
    model = module.NodeModel.__new__(module.NodeModel)
    module.QtCore.QAbstractListModel.__init__(model)
    model.num_items = num_items
    model._items = list(items or [])
    return model


def _row(menupath, score=0, display_text=None, color=(None, None)):
    """Build an item dict matching what NodeModel.update() synthesises."""
    return {
        "text": menupath,
        "display_text": display_text or menupath,
        "menupath": menupath,
        "menuobj": object(),
        "score": score,
        "color": color,
    }


# --- tests --------------------------------------------------------------


def test_no_change_emits_no_row_ops():
    module = _load_core()
    model = _make_model(module, items=[_row("A"), _row("B"), _row("C")])

    model._apply_items([_row("A"), _row("B"), _row("C")])

    assert model.recorded_ops == []
    assert [i["menupath"] for i in model._items] == ["A", "B", "C"]


def test_pure_insertion_into_empty_emits_inserts_in_order():
    module = _load_core()
    model = _make_model(module, items=[])

    model._apply_items([_row("A"), _row("B"), _row("C")])

    assert model.recorded_ops == [
        ("begin_insert", 0, 0), ("end_insert",),
        ("begin_insert", 1, 1), ("end_insert",),
        ("begin_insert", 2, 2), ("end_insert",),
    ]
    assert [i["menupath"] for i in model._items] == ["A", "B", "C"]


def test_pure_removal_walks_back_to_front():
    """Removing back-to-front keeps each emitted index valid at the
    moment Qt sees it; front-to-back would shift indices under us."""
    module = _load_core()
    model = _make_model(module, items=[_row("A"), _row("B"), _row("C")])

    model._apply_items([])

    assert model.recorded_ops == [
        ("begin_remove", 2, 2), ("end_remove",),
        ("begin_remove", 1, 1), ("end_remove",),
        ("begin_remove", 0, 0), ("end_remove",),
    ]
    assert model._items == []


def test_reorder_emits_moves_not_inserts_or_removes():
    module = _load_core()
    model = _make_model(module, items=[_row("A"), _row("B"), _row("C")])

    model._apply_items([_row("C"), _row("A"), _row("B")])

    op_kinds = [op[0] for op in model.recorded_ops]
    assert "begin_remove" not in op_kinds
    assert "begin_insert" not in op_kinds
    assert "begin_move" in op_kinds
    assert [i["menupath"] for i in model._items] == ["C", "A", "B"]


def test_score_change_in_place_emits_data_changed_only():
    module = _load_core()
    model = _make_model(module, items=[_row("A", score=1), _row("B", score=1)])

    model._apply_items([_row("A", score=1), _row("B", score=99)])

    assert model.recorded_ops == [("data_changed", 1, 1)]
    assert model._items[1]["score"] == 99


def test_visually_identical_refresh_emits_nothing():
    """When a refresh produces the same visible fields (display_text,
    score, color) but new dict identity, _row_visually_equal must
    suppress the dataChanged emission. Quiet refreshes are the whole
    point of switching off modelReset — a repaint we don't need is a
    repaint the user can see."""
    module = _load_core()
    model = _make_model(module, items=[_row("A", score=5)])

    model._apply_items([_row("A", score=5)])

    assert model.recorded_ops == []


def test_mixed_remove_insert_and_reorder_orders_removes_first():
    """Removes must precede inserts/moves so that beginInsert/Move
    indices are interpreted against a list whose stale rows are gone."""
    module = _load_core()
    model = _make_model(
        module, items=[_row("A"), _row("B"), _row("C"), _row("D")]
    )

    # Old: A B C D. New: D A E. (B and C removed, E inserted, D moved up.)
    model._apply_items([_row("D"), _row("A"), _row("E")])

    assert [i["menupath"] for i in model._items] == ["D", "A", "E"]

    op_kinds = [op[0] for op in model.recorded_ops]
    last_remove = max(
        (i for i, kind in enumerate(op_kinds) if kind == "begin_remove"),
        default=-1,
    )
    first_struct_after_remove = next(
        (i for i, kind in enumerate(op_kinds)
         if kind in ("begin_insert", "begin_move")),
        len(op_kinds),
    )
    assert last_remove < first_struct_after_remove


def test_off_window_churn_is_silent():
    """Items past num_items aren't visible to Qt (rowCount caps), so
    swapping them emits no row operations."""
    module = _load_core()
    items = [_row(letter) for letter in "ABCDE"]
    model = _make_model(module, num_items=3, items=items)

    # Visible window unchanged (A, B, C); off-window swapped D,E -> F,G.
    model._apply_items([_row("A"), _row("B"), _row("C"), _row("F"), _row("G")])

    assert model.recorded_ops == []
    assert [i["menupath"] for i in model._items] == ["A", "B", "C", "F", "G"]


def test_off_window_item_promoted_into_window_emits_structural_ops():
    """When something previously off-window enters the visible window,
    that crossing must surface — otherwise the user wouldn't see the
    new top-of-list item appear."""
    module = _load_core()
    items = [_row(letter) for letter in "ABCDE"]
    model = _make_model(module, num_items=3, items=items)

    # E was off-window (position 4); now it's at position 0.
    # Visible window must shift from [A, B, C] to [E, A, B].
    model._apply_items([_row("E"), _row("A"), _row("B"), _row("C"), _row("D")])

    op_kinds = [op[0] for op in model.recorded_ops]
    assert "begin_insert" in op_kinds  # E entering the window
    assert "begin_remove" in op_kinds  # C leaving the window
    assert [i["menupath"] for i in model._items[:3]] == ["E", "A", "B"]
