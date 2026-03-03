import tabtabtab_nuke

try:
    tabtabtab_nuke.registerNukeAction()
except Exception:
    import traceback
    traceback.print_exc()
