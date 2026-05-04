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


def test_input_past_num_items_is_equivalent_to_capped_input():
    """new_items past num_items is dead storage — capping at entry
    produces the same signal trace and same final state as if the
    caller had pre-capped the list themselves."""
    module = _load_core()
    full_input = [_row(letter) for letter in "EABCD"]

    model_uncapped = _make_model(module, num_items=3, items=[_row(c) for c in "ABC"])
    model_uncapped._apply_items(full_input)

    model_capped = _make_model(module, num_items=3, items=[_row(c) for c in "ABC"])
    model_capped._apply_items(full_input[:3])

    assert model_uncapped.recorded_ops == model_capped.recorded_ops
    assert (
        [i["menupath"] for i in model_uncapped._items]
        == [i["menupath"] for i in model_capped._items]
    )


def test_pre_existing_off_window_items_are_trimmed_silently():
    """If self._items entered the call with items past num_items (legacy
    state from an older capped-rowCount regime), those are silently
    trimmed before any signal emission so the diff loop's first begin*
    call sees a rowCount that matches reality."""
    module = _load_core()
    # Five items in storage, only three visible — same input as state.
    items = [_row(letter) for letter in "ABCDE"]
    model = _make_model(module, num_items=3, items=items)

    model._apply_items([_row("A"), _row("B"), _row("C")])

    assert model.recorded_ops == []
    assert [i["menupath"] for i in model._items] == ["A", "B", "C"]


def test_self_items_consistent_at_end_of_each_pair():
    """Qt contract: between begin* and end*, the model must mutate its
    backing data so rowCount() reflects the post-operation count by the
    time end* fires. An earlier version mutated a local slice copy and
    only assigned to self._items at the very end of _apply_items, which
    left rowCount() lying through every begin/end pair.

    This test instruments the stub's end* methods to capture
    len(model._items) at the moment each fires and asserts the captured
    counts match the per-step expected sequence — proving the mutation
    is propagating to self._items in step with the signals.
    """
    module = _load_core()
    model = _make_model(module, items=[_row("A"), _row("B"), _row("C")])

    snapshots = []
    original_end_remove = type(model).endRemoveRows
    original_end_insert = type(model).endInsertRows
    original_end_move = type(model).endMoveRows

    def capturing_end_remove(self):
        snapshots.append(("end_remove", len(self._items)))
        original_end_remove(self)

    def capturing_end_insert(self):
        snapshots.append(("end_insert", len(self._items)))
        original_end_insert(self)

    def capturing_end_move(self):
        snapshots.append(("end_move", len(self._items)))
        original_end_move(self)

    model.endRemoveRows = capturing_end_remove.__get__(model, type(model))
    model.endInsertRows = capturing_end_insert.__get__(model, type(model))
    model.endMoveRows = capturing_end_move.__get__(model, type(model))

    # Old: A B C (len 3). New: D A (B and C removed, D inserted at top).
    # Expected snapshots in order:
    #   end_remove → len 2 (C gone)
    #   end_remove → len 1 (B gone)
    #   end_insert → len 2 (D inserted at 0; A still at what's now 1)
    model._apply_items([_row("D"), _row("A")])

    assert snapshots == [
        ("end_remove", 2),
        ("end_remove", 1),
        ("end_insert", 2),
    ]
    assert [i["menupath"] for i in model._items] == ["D", "A"]
