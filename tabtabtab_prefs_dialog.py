try:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (
        QCheckBox,
        QComboBox,
        QDialog,
        QDialogButtonBox,
        QFormLayout,
        QGroupBox,
        QLabel,
        QMessageBox,
        QVBoxLayout,
    )
except ImportError:
    from PySide2.QtCore import Qt
    from PySide2.QtWidgets import (
        QCheckBox,
        QComboBox,
        QDialog,
        QDialogButtonBox,
        QFormLayout,
        QGroupBox,
        QLabel,
        QMessageBox,
        QVBoxLayout,
    )

import tabtabtab_nuke
import tabtabtab_nuke_core
import tabtabtab_prefs

# PySide2 exposes the item-data roles directly on Qt; PySide6 nests them under
# Qt.ItemDataRole (and only keeps the shorthand when built with forgiving enums).
TOOLTIP_ROLE = getattr(Qt, "ToolTipRole", None)
if TOOLTIP_ROLE is None:
    TOOLTIP_ROLE = Qt.ItemDataRole.ToolTipRole

MODE_LABELS = {
    tabtabtab_nuke_core.MODE_ANCHORED_FUZZY: "Anchored fuzzy",
    tabtabtab_nuke_core.MODE_NON_ANCHORED_FUZZY: "Non-anchored fuzzy",
    tabtabtab_nuke_core.MODE_CONSECUTIVE: "Consecutive substring",
}

# One source of truth for the group's explainer text and the per-option
# tooltips, so the two can never drift apart. The examples are verified against
# consec_find/nonconsec_find in tabtabtab_nuke_core and match the readme's
# "Search modes" table.
MODE_DESCRIPTIONS = {
    tabtabtab_nuke_core.MODE_ANCHORED_FUZZY: (
        "The letters you type must appear in order, starting from the first "
        'letter of the node name. "blr" finds "Blur" but not "MotionBlur".'
    ),
    tabtabtab_nuke_core.MODE_NON_ANCHORED_FUZZY: (
        "The letters you type must appear in order, but can start anywhere in "
        'the node name. "blr" finds both "Blur" and "MotionBlur".'
    ),
    tabtabtab_nuke_core.MODE_CONSECUTIVE: (
        "The letters you type must appear as one unbroken run anywhere in the "
        'node name. "blur" finds both "Blur" and "MotionBlur", while "blr" '
        "finds neither, because its letters are not adjacent."
    ),
}

SPACE_ROW_LABELS = [
    "No leading space:",
    "One leading space:",
    "Two leading spaces:",
]

SPACE_ROW_TOOLTIPS = [
    "The mode used when your search text has no leading space.",
    "The mode used when your search text has exactly one leading space.",
    "The mode used when your search text has two leading spaces.",
]


class TabtabtabPrefsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Tabtabtab Preferences")
        self._build_ui()
        self._populate_from_prefs()

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        form_layout = QFormLayout()
        main_layout.addLayout(form_layout)

        self.tabtabtab_enabled_checkbox = QCheckBox()
        self.tabtabtab_enabled_checkbox.setToolTip(
            "When unchecked, Tabtabtab is disabled entirely and Nuke's default "
            "Tab key behavior is restored. Takes effect immediately."
        )
        form_layout.addRow("Enable Tabtabtab:", self.tabtabtab_enabled_checkbox)

        self.scroll_enabled_checkbox = QCheckBox()
        self.scroll_enabled_checkbox.setToolTip(
            "When checked, the results list keeps more matches than fit in the "
            "popup window and lets you scroll (or arrow-key) through the rest "
            "instead of hiding them. The popup window stays the same size "
            "either way. When unchecked, only the first screenful of matches "
            "is kept, matching the previous behavior. Takes effect on the "
            "next time Tabtabtab is opened."
        )
        form_layout.addRow("Enable scrolling through results:", self.scroll_enabled_checkbox)

        # Space-prefix mode mapping
        mode_group = QGroupBox("Space-prefix search modes")
        mode_group.setToolTip(
            "Typing 0, 1, or 2 spaces before your search text picks a different "
            "matching mode. Each row below sets which mode that number of "
            "leading spaces uses."
        )
        mode_layout = QVBoxLayout()
        mode_group.setLayout(mode_layout)

        intro_label = QLabel(
            "Type this many spaces before your search text to use that row's mode:"
        )
        intro_label.setWordWrap(True)
        mode_layout.addWidget(intro_label)

        combo_layout = QFormLayout()
        mode_layout.addLayout(combo_layout)

        all_modes = list(tabtabtab_nuke_core.DEFAULT_SPACE_MODE_ORDER)

        self._space_combos = []
        for space_label, row_tooltip in zip(SPACE_ROW_LABELS, SPACE_ROW_TOOLTIPS):
            combo = QComboBox()
            combo.setToolTip(row_tooltip)
            for mode_id in all_modes:
                combo.addItem(MODE_LABELS[mode_id], mode_id)
                combo.setItemData(
                    combo.count() - 1, MODE_DESCRIPTIONS[mode_id], TOOLTIP_ROLE
                )
            combo_layout.addRow(space_label, combo)
            self._space_combos.append(combo)

        # Describe every mode once, always visible, rather than per row: the
        # descriptions are fixed, so text tied to a row would just shuffle
        # around as the user remaps the modes.
        blurb_label = QLabel(
            "\n\n".join(
                "%s — %s" % (MODE_LABELS[mode_id], MODE_DESCRIPTIONS[mode_id])
                for mode_id in all_modes
            )
        )
        blurb_label.setWordWrap(True)
        mode_layout.addWidget(blurb_label)

        main_layout.addWidget(mode_group)

        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self._on_accept)
        button_box.rejected.connect(self.reject)
        main_layout.addWidget(button_box)

    def _populate_from_prefs(self):
        prefs = tabtabtab_prefs.prefs_singleton
        self.tabtabtab_enabled_checkbox.setChecked(bool(prefs.get("tabtabtab_enabled")))
        self.scroll_enabled_checkbox.setChecked(bool(prefs.get("scroll_enabled")))

        space_mode_order = prefs.get("space_mode_order")
        for i, combo in enumerate(self._space_combos):
            idx = combo.findData(space_mode_order[i])
            if idx >= 0:
                combo.setCurrentIndex(idx)

    def _on_accept(self):
        prefs = tabtabtab_prefs.prefs_singleton

        space_mode_order = [combo.currentData() for combo in self._space_combos]
        if len(set(space_mode_order)) < 3:
            QMessageBox.warning(
                self,
                "Invalid configuration",
                "Each search mode must be assigned to exactly one space level.",
            )
            return

        enabled = self.tabtabtab_enabled_checkbox.isChecked()
        prefs.set("tabtabtab_enabled", enabled)
        prefs.set("scroll_enabled", self.scroll_enabled_checkbox.isChecked())
        prefs.set("space_mode_order", space_mode_order)
        prefs.save()
        if enabled:
            tabtabtab_nuke.registerNukeAction()
        else:
            tabtabtab_nuke.unregisterNukeAction()
        self.accept()


def show_prefs_dialog():
    dialog = TabtabtabPrefsDialog()
    dialog.exec()
