from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QVBoxLayout,
)

import tabtabtab_nuke
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

        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self._on_accept)
        button_box.rejected.connect(self.reject)
        main_layout.addWidget(button_box)

    def _populate_from_prefs(self):
        prefs = tabtabtab_prefs.prefs_singleton
        self.tabtabtab_enabled_checkbox.setChecked(bool(prefs.get("tabtabtab_enabled")))

    def _on_accept(self):
        prefs = tabtabtab_prefs.prefs_singleton
        enabled = self.tabtabtab_enabled_checkbox.isChecked()
        prefs.set("tabtabtab_enabled", enabled)
        prefs.save()
        if enabled:
            tabtabtab_nuke.registerNukeAction()
        else:
            tabtabtab_nuke.unregisterNukeAction()
        self.accept()


def show_prefs_dialog():
    dialog = TabtabtabPrefsDialog()
    dialog.exec()
