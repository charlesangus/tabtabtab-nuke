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

        # Space-prefix mode mapping
        mode_group = QGroupBox("Space-prefix search modes")
        mode_group.setToolTip(
            "In the search box, typing 0, 1, or 2 spaces before your text selects a "
            "different matching mode. Each row below controls which mode is used for "
            "that number of leading spaces."
        )
        mode_layout = QVBoxLayout()
        mode_group.setLayout(mode_layout)

        mode_explainer = QLabel(
            "Type this many spaces before your search text in the tabtabtab popup to "
            "use the mode selected on that row:"
        )
        mode_explainer.setWordWrap(True)
        mode_layout.addWidget(mode_explainer)

        mode_labels = {
            tabtabtab_nuke_core.MODE_ANCHORED_FUZZY: "Anchored fuzzy",
            tabtabtab_nuke_core.MODE_NON_ANCHORED_FUZZY: "Non-anchored fuzzy",
            tabtabtab_nuke_core.MODE_CONSECUTIVE: "Consecutive substring",
        }
        # Explains what each mode actually does when matching, with the same
        # examples/wording used in the readme's "Search modes" table so the
        # two stay consistent.
        mode_descriptions = {
            tabtabtab_nuke_core.MODE_ANCHORED_FUZZY: (
                "Anchored fuzzy: each character you type must appear in order, "
                'starting from the beginning of the node name. "blr" matches '
                '"Blur" but not "ColorBurn".'
            ),
            tabtabtab_nuke_core.MODE_NON_ANCHORED_FUZZY: (
                "Non-anchored fuzzy: characters must appear in order, but can "
                'start anywhere in the name. "blr" matches both "Blur" and '
                '"ColorBurn".'
            ),
            tabtabtab_nuke_core.MODE_CONSECUTIVE: (
                "Consecutive substring: the exact run of letters you type must "
                'appear together somewhere in the name. "blur" matches '
                '"MotionBlur" but not "Blur2".'
            ),
        }
        all_modes = list(tabtabtab_nuke_core.DEFAULT_SPACE_MODE_ORDER)

        combo_form = QFormLayout()
        mode_layout.addLayout(combo_form)

        space_row_tooltips = {
            0: "Mode used when your search text has no leading space.",
            1: "Mode used when your search text has exactly one leading space.",
            2: "Mode used when your search text has two (or more) leading spaces.",
        }

        self._space_combos = []
        self._space_descriptions = []
        for level, space_label in enumerate(
            ["No leading space:", "One leading space:", "Two leading spaces:"]
        ):
            combo = QComboBox()
            combo.setToolTip(space_row_tooltips[level])
            for mode_id in all_modes:
                combo.addItem(mode_labels[mode_id], mode_id)
                combo.setItemData(
                    combo.count() - 1, mode_descriptions[mode_id], Qt.ToolTipRole
                )
            combo_form.addRow(space_label, combo)
            self._space_combos.append(combo)

            description_label = QLabel()
            description_label.setWordWrap(True)
            description_font = description_label.font()
            description_font.setItalic(True)
            description_font.setPointSize(max(description_font.pointSize() - 1, 1))
            description_label.setFont(description_font)
            combo_form.addRow("", description_label)
            self._space_descriptions.append(description_label)

            combo.currentIndexChanged.connect(
                lambda _idx, c=combo, lbl=description_label: lbl.setText(
                    mode_descriptions.get(c.currentData(), "")
                )
            )
            description_label.setText(mode_descriptions.get(combo.currentData(), ""))

        main_layout.addWidget(mode_group)

        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self._on_accept)
        button_box.rejected.connect(self.reject)
        main_layout.addWidget(button_box)

    def _populate_from_prefs(self):
        prefs = tabtabtab_prefs.prefs_singleton
        self.tabtabtab_enabled_checkbox.setChecked(bool(prefs.get("tabtabtab_enabled")))

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
