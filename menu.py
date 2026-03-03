import nuke
import tabtabtab_nuke
import tabtabtab_prefs
import tabtabtab_prefs_dialog

try:
    if tabtabtab_prefs.prefs_singleton.get("tabtabtab_enabled"):
        tabtabtab_nuke.registerNukeAction()
except Exception:
    import traceback
    traceback.print_exc()

edit_menu = nuke.menu("Nuke").findItem("Edit")
edit_menu.addCommand("Tabtabtab Preferences...", tabtabtab_prefs_dialog.show_prefs_dialog)
