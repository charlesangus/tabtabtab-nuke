# tabtabtab

A fuzzy/substring node creator for [The Foundry's Nuke](https://www.foundry.com/products/nuke).

- Fuzzy and substring matching — type "blr" to match "Blur", "trge" to match "TransformGeo"
- Each result row is tinted with the node's tile color from Nuke (Merge nodes are red, Color
  nodes are orange, etc.), making it easy to visually identify node categories at a glance
- Weights frequently-used nodes so they appear first in results
- Exposes all menu items, not just nodes — type "exit" to trigger File > Exit

Ctrl+Tab still opens Nuke's built-in tab menu.


# Installation

Clone or copy the `tabtabtab-nuke` directory into your Nuke plugin path (e.g. `~/.nuke/`).
You can either add it to `NUKE_PATH` in your environment, or put the folder directly in `~/.nuke/`.

The included `menu.py` will auto-register tabtabtab when Nuke starts. No further configuration
is needed.


# Preferences

Open `Edit > Tabtabtab Preferences...` to access the preferences dialog. Currently this exposes:

- **Enable tabtabtab** — check or uncheck to enable or disable the plugin

Changes take effect immediately without restarting Nuke.


# Search modes

| Prefix | Behavior |
|--------|----------|
| (none) | Fuzzy, anchored to first letter — "blr" matches "Blur" but not "Blur2 [Filter]" via middle letters |
| one space | Fuzzy, non-anchored — matches the pattern anywhere in the node name |
| two spaces | Non-fuzzy consecutive substring, non-anchored — matches an exact run of letters anywhere |

**Category matching:** typing `[` anywhere in your search includes the `[Category]` part of the
menu path. For example, "ax" matches both "AddMix [Merge]" and "Axis [3D]". Typing "ax[3d" will
narrow that to only "Axis [3D]".


# Keyboard shortcuts

| Key | Action |
|-----|--------|
| Tab or Enter | Create the selected node |
| Up / Down | Navigate the result list |
| Escape | Cancel and close |

The last search text is preserved — pressing Tab twice (opening tabtabtab with no typing) will
recreate the previously created node.


# Weighting

Each time you create a node, its weight increases. Higher-weighted nodes appear earlier in the
result list when multiple nodes match your search. Weights are saved between sessions.

There is no visual indicator of node weight; weighting affects ranking order only.


# Node colors

Each result row is tinted with the node's tile color as defined in Nuke. The left column shows a
solid block of the node's tile color, and the row background gets a semi-transparent wash of the
same color. This makes it easy to visually distinguish node categories without reading the full
name.


# Notes

Requires Nuke 9 or higher. Tested with PySide6 (Nuke 16+).


# Change log

* `v2.0`
  * Rewritten as a plugin architecture: shared core engine (`tabtabtab-core`) with a
    Nuke-specific frontend
  * Added preferences system (`Edit > Tabtabtab Preferences...`) with enable/disable toggle
  * Node tile colors shown in result rows (solid color block + semi-transparent row background)
  * `menu.py` included for zero-config installation via plugin path
  * Nuke 16 / PySide6 support
  * Search mode prefixes changed to leading spaces (one space = non-anchored fuzzy,
    two spaces = consecutive substring)

* `v1.9`
  * Integrating changes from @herronelou and @nrusch

* `v1.8`
  * Installation instructions updated to support Nuke 9
  * Weights file no longer overwritten if it fails to load
  * Support PySide2

* `v1.7`
  * `ToolSets/Delete` submenu excluded from results
  * Fixed bug which caused the node list to stop updating
  * Fixed bug where "last used node" might match a different node

* `v1.6`
  * Search string starting with space disables non-consecutive searching
  * Exposes menu items in `nuke.menu("Nuke")` (File menu, etc.)

* `v1.5`
  * Window closes properly

* `v1.4`
  * Blocks Nuke UI when active
  * Up/down arrow keys cycle correctly
  * Node weights now actually indicated (not always green)

* `v1.3`
  * Created node remains selected between tabs ("tabtab" recreates previous node)
  * Clicking a node creates it
  * Window stays on screen near edges

* `v1.2`
  * Window appears under cursor

* `v1.1`
  * Node weights are saved

* `v1.0`
  * Initial release
