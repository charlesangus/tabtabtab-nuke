"""tabtabtab — app-agnostic command palette core

homepage: https://github.com/dbr/tabtabtab-nuke
license: http://unlicense.org/
"""

__version__ = "2.0"

import os
import re

try:
    from PySide6 import QtCore, QtGui, QtWidgets
    from PySide6.QtCore import Qt
except ImportError:
    from PySide2 import QtCore, QtGui, QtWidgets
    from PySide2.QtCore import Qt


# Search mode identifiers used by the space-prefix mapping preference.
MODE_ANCHORED_FUZZY = "anchored_fuzzy"
MODE_NON_ANCHORED_FUZZY = "non_anchored_fuzzy"
MODE_CONSECUTIVE = "consecutive"

VALID_MODES = {MODE_ANCHORED_FUZZY, MODE_NON_ANCHORED_FUZZY, MODE_CONSECUTIVE}

DEFAULT_SPACE_MODE_ORDER = [
    MODE_ANCHORED_FUZZY,       # 0 spaces (default)
    MODE_NON_ANCHORED_FUZZY,   # 1 space
    MODE_CONSECUTIVE,          # 2 spaces
]


class TabTabTabPlugin:
    def get_items(self):
        """Return list of {'menuobj': ..., 'menupath': str} dicts."""
        raise NotImplementedError

    def get_weights_file(self):
        """Return path to JSON weights file, or None to skip persistence."""
        raise NotImplementedError

    def invoke(self, thing):
        """Trigger the selected menu item."""
        raise NotImplementedError

    def get_icon(self, menuobj):
        """Return a QIcon for menuobj, or None.
        Default works for any Qt object whose .icon() returns a QIcon."""
        try:
            icon = menuobj.icon()
            if isinstance(icon, QtGui.QIcon) and not icon.isNull():
                return icon
        except Exception:
            pass
        return None

    def get_color(self, menuobj):
        """Return a (left_block_color, text_tint_color) tuple of QtGui.QColor or None.

        left_block_color: solid colour filling the icon-width column on the left.
          Use None when an icon is present (or when no left-block colour is wanted).
        text_tint_color: semi-transparent wash applied only behind the text area,
          also controls foreground text colour via luminance.
        Either element may be None to suppress that part of the colouring.
        """
        return (None, None)

    def invalidate_cache(self):
        """Optional hook called after the popup closes so the next get_items()
        and get_color() return fresh data.

        Override to drop any plugin-side caches (e.g., a recursive menu walk
        or per-class colour memoisation). Default is a no-op for plugins that
        don't cache.
        """
        pass


def _normalize_qt_item_name(item):
    item_name = item.text()
    item_name = item_name.replace("&", "")
    item_name = re.sub(r'^\s*\d+ \s*', '', item_name).strip()
    return item_name


def _traverse_qt_menu(menu, _path=None):
    """Recursively traverse a QMenu, returning list of {'menuobj', 'menupath'} dicts."""
    found = []

    if not menu.isEnabled():
        return []

    for item in menu.actions():
        if not (item.isVisible() and item.isEnabled()):
            continue

        item_name = _normalize_qt_item_name(item)
        submenu = item.menu()

        if submenu:
            subpath = "/".join(x for x in (_path, item_name) if x is not None)
            found.extend(_traverse_qt_menu(submenu, _path=subpath))
        else:
            if item.data() == "":
                # skip if no actual action
                continue
            if item.text() == "":
                # Skip dividers
                continue

            subpath = "/".join(x for x in (_path, item_name) if x is not None)
            found.append({'menuobj': item, 'menupath': subpath})

    return found


def find_qt_menu_items(menubar):
    """Traverse a QMenuBar and return all leaf menu items.

    Returns a list of {'menuobj': QAction, 'menupath': str} dicts.
    Usable by any Qt app plugin without importing anything app-specific.
    """
    items = []
    for action in menubar.actions():
        if action.menu():
            items.extend(_traverse_qt_menu(action.menu(), _path=action.text()))
    return items


def consec_find(needle, haystack, anchored=False):
    ''' searches for the "needle" string in the "haystack" string.
        added to tabtabtab as a way to prioritize more relevant results.
    '''

    if "[" not in needle:
        haystack = haystack.rpartition(" [")[0]

    stripped_haystack = haystack.replace(' ', '').replace('-', '').replace('_', '')

    if anchored:
        if haystack.startswith(needle) or stripped_haystack.startswith(needle):
            return True

    else:
        if needle in haystack or needle in stripped_haystack:
            return True
    return False


def nonconsec_find(needle, haystack, anchored=False):
    """checks if each character of "needle" can be found in order (but not
    necessarily consecutivly) in haystack.
    For example, "mm" can be found in "matchmove", but not "move2d"
    "m2" can be found in "move2d", but not "matchmove"

    >>> nonconsec_find("m2", "move2d")
    True
    >>> nonconsec_find("m2", "matchmove")
    False

    Anchored ensures the first letter matches

    >>> nonconsec_find("atch", "matchmove", anchored = False)
    True
    >>> nonconsec_find("atch", "matchmove", anchored = True)
    False
    >>> nonconsec_find("match", "matchmove", anchored = True)
    True

    If needle starts with a string, non-consecutive searching is disabled:

    >>> nonconsec_find(" mt", "matchmove", anchored = True)
    False
    >>> nonconsec_find(" ma", "matchmove", anchored = True)
    True
    >>> nonconsec_find(" oe", "matchmove", anchored = False)
    False
    >>> nonconsec_find(" ov", "matchmove", anchored = False)
    True
    """

    if "[" not in needle:
        haystack = haystack.rpartition(" [")[0]

    if len(haystack) == 0 and len(needle) > 0:
        # "a" is not in ""
        return False

    elif len(needle) == 0 and len(haystack) > 0:
        # "" is in "blah"
        return True

    elif len(needle) == 0 and len(haystack) == 0:
        # ..?
        return True

    # Turn haystack into list of characters (as strings are immutable)
    haystack = [hay for hay in str(haystack)]

    if needle.startswith(" "):
        # "[space]abc" does consecutive search for "abc" in "abcdef"
        if anchored:
            if "".join(haystack).startswith(needle.lstrip(" ")):
                return True
        else:
            if needle.lstrip(" ") in "".join(haystack):
                return True

    if anchored:
        if needle[0] != haystack[0]:
            return False
        else:
            # First letter matches, remove it for further matches
            needle = needle[1:]
            del haystack[0]

    for needle_atom in needle:
        try:
            needle_pos = haystack.index(needle_atom)
        except ValueError:
            return False
        else:
            # Dont find string in same pos or backwards again
            del haystack[:needle_pos + 1]
    return True


class NodeWeights(object):
    def __init__(self, fname=None):
        self.fname = fname
        self._weights = {}
        self._successful_load = False

    def load(self):
        if self.fname is None:
            return

        def _load_internal():
            import json
            if not os.path.isfile(self.fname):
                print("Weight file does not exist")
                return
            f = open(self.fname)
            self._weights = json.load(f)
            f.close()

        # Catch any errors, print traceback and continue
        try:
            _load_internal()
            self._successful_load = True
        except Exception:
            print("Error loading node weights.")
            import traceback
            traceback.print_exc()
            self._successful_load = False

    def save(self):
        if self.fname is None:
            print("Not saving node weights, no file specified")
            return

        if not self._successful_load:
            # Avoid clobbering existing weights file on load error
            print(("Not writing weights file because %r previously failed to load" % (
                self.fname)))
            return

        def _save_internal():
            import json
            ndir = os.path.dirname(self.fname)
            if not os.path.isdir(ndir):
                try:
                    os.makedirs(ndir)
                except OSError as e:
                    if e.errno != 17:  # errno 17 is "already exists"
                        raise

            f = open(self.fname, "w")
            # TODO: Limit number of saved items to some sane number
            json.dump(self._weights, fp=f)
            f.close()

        # Catch any errors, print traceback and continue
        try:
            _save_internal()
        except Exception:
            print("Error saving node weights")
            import traceback
            traceback.print_exc()

    def get(self, k, default=0):
        if len(list(self._weights.values())) == 0:
            maxval = 1.0
        else:
            maxval = max(self._weights.values())
            maxval = max(1, maxval)
            maxval = float(maxval)

        return self._weights.get(k, default) / maxval

    def increment(self, key):
        self._weights.setdefault(key, 0)
        self._weights[key] += 1


class NodeModel(QtCore.QAbstractListModel):
    def __init__(self, mlist, weights, num_items=18, filtertext="", icon_fn=None, color_fn=None, space_mode_order=None):
        super(NodeModel, self).__init__()

        self.weights = weights
        self.num_items = num_items

        self._all = mlist
        self._filtertext = filtertext
        self._icon_fn = icon_fn if icon_fn is not None else (lambda obj: None)
        self._color_fn = color_fn if color_fn is not None else (lambda obj: (None, None))

        if (space_mode_order is not None
                and len(space_mode_order) == len(DEFAULT_SPACE_MODE_ORDER)
                and all(m in VALID_MODES for m in space_mode_order)):
            self._space_mode_order = list(space_mode_order)
        else:
            self._space_mode_order = list(DEFAULT_SPACE_MODE_ORDER)

        # _items is the list of objects to be shown, update sets this
        self._items = []
        self.update()

    def set_filter(self, filtertext):
        self._filtertext = filtertext
        self.update()

    def refresh_items(self, mlist):
        self._all = mlist
        self.update()

    def update(self):
        filtertext = self._filtertext.lower()

        anchored = True
        force_non_anchored = False
        force_consecutive = False

        # Determine space-prefix level (0, 1, or 2 leading spaces)
        if filtertext.startswith('  '):
            space_level = 2
            filtertext = filtertext[2:]
        elif filtertext.startswith(' '):
            space_level = 1
            filtertext = filtertext[1:]
        # * or [ prefix: non-anchored fuzzy (legacy shortcuts, unchanged)
        elif filtertext.startswith('*') or filtertext.startswith('['):
            space_level = None
            anchored = False
            filtertext = filtertext.replace("*", "", 1)
            if filtertext.startswith('*'):
                force_non_anchored = True
            filtertext = filtertext.replace("*", "")
        else:
            space_level = 0

        # Apply mode from the configurable space-prefix mapping
        if space_level is not None:
            mode = self._space_mode_order[space_level]
            if mode == MODE_ANCHORED_FUZZY:
                anchored = True
            elif mode == MODE_NON_ANCHORED_FUZZY:
                anchored = False
            elif mode == MODE_CONSECUTIVE:
                anchored = False
                force_consecutive = True

        scored_a = []
        scored_b = []
        for n in self._all:
            # Turn "3D/Shader/Phong" into "Phong [3D/Shader]"
            menupath = n['menupath'].replace("&", "")
            uiname = "%s [%s]" % (menupath.rpartition("/")[2], menupath.rpartition("/")[0])
            search_string = uiname.lower()

            if force_non_anchored:
                search_string = search_string[1:]

            shortcut = n.get('shortcut')
            display_text = "%s (%s)" % (uiname, shortcut) if shortcut else uiname

            if consec_find(filtertext, search_string, anchored):
                # Matches, get weighting and add to list of stuff
                score = self.weights.get(n['menupath'])

                scored_a.append({
                    'text': uiname,
                    'display_text': display_text,
                    'menupath': n['menupath'],
                    'menuobj': n['menuobj'],
                    'score': score,
                    'color': self._color_fn(n['menuobj'])})

            elif not force_consecutive and nonconsec_find(filtertext, search_string, anchored):
                # Matches, get weighting and add to list of stuff
                score = self.weights.get(n['menupath'])

                scored_b.append({
                    'text': uiname,
                    'display_text': display_text,
                    'menupath': n['menupath'],
                    'menuobj': n['menuobj'],
                    'score': score,
                    'color': self._color_fn(n['menuobj'])})

        # Sort based on scores (descending), then alphabetically
        sort_a = sorted(scored_a, key=lambda k: (-k['score'], k['text']))
        sort_b = sorted(scored_b, key=lambda k: (-k['score'], k['text']))
        s = sort_a + sort_b

        self._apply_items(s)

    def _apply_items(self, new_items):
        """Replace visible items via minimal row operations instead of a
        full modelReset.

        Mutates self._items in place between every begin*/end* pair so
        rowCount() reflects the post-mutation state by the time end* is
        called — that's the Qt contract. An earlier version mutated a
        local slice copy, leaving self._items stale through the whole
        run; views querying mid-emission saw inconsistent state.

        Diff is keyed on `menupath` (each item's stable identity).
        new_items is capped at num_items at entry; everything past that
        is dead storage (data()/getorig() never read past rowCount, and
        update() rebuilds from self._all so off-window retention buys
        nothing). rowCount() now returns len(self._items) directly.

        Why this matters: the deferred refresh on popup show ran
        modelReset twice (cheap pass + fresh re-walk), blanking the
        view and clearing selection. Row ops keep the view stable —
        the user sees the previous open's items immediately and they
        morph into current as the timers tick.
        """
        parent = QtCore.QModelIndex()
        n = self.num_items
        # Cap both lists at the visible window. self._items may have
        # been longer under the previous (capped-rowCount) regime; trim
        # silently before any signal emission so the diff loop's first
        # begin* call sees a consistent rowCount.
        if len(self._items) > n:
            del self._items[n:]
        new_items = new_items[:n]

        new_key_set = {item['menupath'] for item in new_items}

        # Remove rows whose key is no longer present, walking back-to-
        # front so earlier indices stay valid as we delete.
        for i in range(len(self._items) - 1, -1, -1):
            if self._items[i]['menupath'] not in new_key_set:
                self.beginRemoveRows(parent, i, i)
                del self._items[i]
                self.endRemoveRows()

        # Walk the target order. At each position, ensure the right row
        # is present — moving an existing one up, or inserting a new one.
        for target_pos, new_item in enumerate(new_items):
            key = new_item['menupath']

            if (target_pos < len(self._items)
                    and self._items[target_pos]['menupath'] == key):
                if not self._row_visually_equal(self._items[target_pos], new_item):
                    self._items[target_pos] = new_item
                    idx = self.index(target_pos)
                    self.dataChanged.emit(idx, idx)
                continue

            source_pos = None
            for j in range(target_pos + 1, len(self._items)):
                if self._items[j]['menupath'] == key:
                    source_pos = j
                    break

            if source_pos is not None:
                # source_pos > target_pos always here, so destinationChild
                # = target_pos is a valid move (Qt rejects no-op moves
                # where dest == source or source + 1). beginMoveRows
                # returns False if Qt rejects anyway; fall back to
                # remove+insert so we never run endMoveRows against a
                # rejected begin.
                moved = self.beginMoveRows(
                    parent, source_pos, source_pos, parent, target_pos
                )
                if moved:
                    self._items.insert(target_pos, self._items.pop(source_pos))
                    self.endMoveRows()
                    if not self._row_visually_equal(self._items[target_pos], new_item):
                        self._items[target_pos] = new_item
                        idx = self.index(target_pos)
                        self.dataChanged.emit(idx, idx)
                else:
                    self.beginRemoveRows(parent, source_pos, source_pos)
                    del self._items[source_pos]
                    self.endRemoveRows()
                    self.beginInsertRows(parent, target_pos, target_pos)
                    self._items.insert(target_pos, new_item)
                    self.endInsertRows()
            else:
                self.beginInsertRows(parent, target_pos, target_pos)
                self._items.insert(target_pos, new_item)
                self.endInsertRows()

    @staticmethod
    def _row_visually_equal(old_row, new_row):
        """True if two rows would render identically. Compares only the
        fields the delegate reads — skipping `menuobj` (host handle,
        identity comparison is unreliable) and `menupath` (already
        matched by caller)."""
        return (
            old_row.get('display_text') == new_row.get('display_text')
            and old_row.get('score') == new_row.get('score')
            and old_row.get('color') == new_row.get('color')
        )

    def rowCount(self, parent=QtCore.QModelIndex()):
        return len(self._items)

    def data(self, index, role=Qt.DisplayRole):
        if role == Qt.DisplayRole:
            item = self._items[index.row()]
            return item.get('display_text', item['text'])

        elif role == Qt.DecorationRole:
            icon = self._icon_fn(self._items[index.row()]['menuobj'])
            if isinstance(icon, QtGui.QIcon) and not icon.isNull():
                return icon
            return None

        elif role == Qt.BackgroundRole:
            left_block_color, text_tint_color = self._items[index.row()]['color']
            if text_tint_color is None:
                return None
            tinted = QtGui.QColor(text_tint_color.red(), text_tint_color.green(), text_tint_color.blue(), 80)  # 31% opacity
            return QtGui.QBrush(tinted)

        elif role == Qt.ForegroundRole:
            _, text_tint_color = self._items[index.row()]['color']
            if text_tint_color is None:
                return None
            luminance = 0.299 * text_tint_color.red() + 0.587 * text_tint_color.green() + 0.114 * text_tint_color.blue()
            if luminance > 160:
                return QtGui.QBrush(QtGui.QColor(40, 40, 40))
            else:
                return QtGui.QBrush(QtGui.QColor(220, 220, 220))

        elif role == Qt.UserRole:
            left_block_color, _ = self._items[index.row()]['color']
            return left_block_color

        else:
            return None

    def getorig(self, selected):
        # TODO: Is there a way to get this via data()? There's no
        # Qt.DataRole or something (only DisplayRole)

        if len(selected) > 0:
            # Get first selected index
            selected = selected[0]

        else:
            # Nothing selected, get first index
            selected = self.index(0)

        # TODO: Maybe check for IndexError?
        selected_data = self._items[selected.row()]
        return selected_data


class TabyLineEdit(QtWidgets.QLineEdit):
    pressed_arrow = QtCore.Signal(str)
    cancelled = QtCore.Signal()

    def event(self, event):
        """Make tab trigger returnPressed

        Also emit signals for the up/down arrows, and escape.
        """

        is_keypress = event.type() == QtCore.QEvent.KeyPress

        if is_keypress and event.key() == QtCore.Qt.Key_Tab:
            # Can't access tab key in keyPressedEvent
            self.returnPressed.emit()
            return True

        elif is_keypress and event.key() == QtCore.Qt.Key_Up:
            # These could be done in keyPressedEvent, but.. this is already here
            self.pressed_arrow.emit("up")
            return True

        elif is_keypress and event.key() == QtCore.Qt.Key_Down:
            self.pressed_arrow.emit("down")
            return True

        elif is_keypress and event.key() == QtCore.Qt.Key_Escape:
            self.cancelled.emit()
            return True

        else:
            return super(TabyLineEdit, self).event(event)


class _ItemDelegate(QtWidgets.QStyledItemDelegate):
    """Custom delegate: fixed row height, full-width tinted background,
    solid colour icon block, and outline-only selection highlight."""

    def __init__(self, height, icon_w, parent=None):
        super(_ItemDelegate, self).__init__(parent)
        self._height = height
        self._icon_w = icon_w

    def sizeHint(self, option, index):
        sh = super(_ItemDelegate, self).sizeHint(option, index)
        return QtCore.QSize(sh.width(), self._height)

    def paint(self, painter, option, index):
        painter.save()
        rect = option.rect

        # Determine what occupies the left icon column so we can compute the
        # text rect before drawing anything (the background wash uses it).
        left_block_color = index.data(Qt.UserRole)  # solid colour block, or None
        icon = index.data(Qt.DecorationRole)
        has_icon = isinstance(icon, QtGui.QIcon) and not icon.isNull()

        # Always reserve the left block space — text is always indented the same amount.
        text_left = rect.left() + self._icon_w + 6
        text_rect = QtCore.QRect(text_left, rect.top(), rect.right() - text_left, rect.height())

        # 1. Tinted background wash — from the right edge of the left block to
        # the end of the row, so there is no uncoloured gap before the text.
        bg_brush = index.data(Qt.BackgroundRole)
        if bg_brush is not None:
            bg_left = rect.left() + self._icon_w
            bg_rect = QtCore.QRect(bg_left, rect.top(), rect.right() - bg_left, rect.height())
            painter.fillRect(bg_rect, bg_brush)

        # 2. Left icon column: solid colour block as background (neutral grey when no colour),
        # then QIcon on top.
        icon_rect = QtCore.QRect(rect.left(), rect.top(), self._icon_w, rect.height())
        block_fill = left_block_color if left_block_color is not None else QtGui.QColor(50, 50, 50)
        painter.fillRect(icon_rect, block_fill)
        if has_icon:
            icon_size = min(self._icon_w, rect.height()) - 4
            icon_x = rect.left() + (self._icon_w - icon_size) // 2
            icon_y = rect.top() + (rect.height() - icon_size) // 2
            icon.paint(painter, icon_x, icon_y, icon_size, icon_size)

        # 3. Selection as outline only (1px border, highlight colour)
        if option.state & QtWidgets.QStyle.State_Selected:
            pen = QtGui.QPen(option.palette.highlight().color(), 1)
            painter.setPen(pen)
            painter.drawRect(rect.adjusted(0, 0, -1, -1))

        # 4. Text
        fg = index.data(Qt.ForegroundRole)
        painter.setPen(fg.color() if fg else option.palette.text().color())
        text = index.data(Qt.DisplayRole) or ""
        painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, text)

        painter.restore()


class TabTabTabWidget(QtWidgets.QDialog):
    def __init__(self, plugin, parent=None, winflags=None, space_mode_order=None):
        super(TabTabTabWidget, self).__init__(parent=parent)
        if winflags is not None:
            self.setWindowFlags(winflags)

        self.plugin = plugin

        # Input box
        self.input = TabyLineEdit()

        # Node weighting
        self.weights = NodeWeights(plugin.get_weights_file())
        self.weights.load()  # weights.save() called in close method

        items = plugin.get_items()

        # List of stuff, and associated model
        self.things_model = NodeModel(items, weights=self.weights, icon_fn=plugin.get_icon, color_fn=plugin.get_color, space_mode_order=space_mode_order)
        self.things = QtWidgets.QListView()
        self.things.setModel(self.things_model)
        self.things.setUniformItemSizes(True)
        self.input.setFont(self.things.font())

        _font_h = self.things.fontMetrics().height()
        _row_h = _font_h * 2
        self.things.setItemDelegate(_ItemDelegate(_row_h, _row_h, self.things))
        self.things.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.input.setTextMargins(2, _font_h // 2, 2, _font_h // 2)

        # Add input and items to layout
        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(self.input)
        layout.addWidget(self.things)

        self.setLayout(layout)

        # Update on text change
        self.input.textChanged.connect(self.update)

        # Reset selection on text change
        self.input.textChanged.connect(lambda: self.move_selection(where="first"))
        self.move_selection(where="first")  # Set initial selection

        # Create node when enter/tab is pressed, or item is clicked
        self.input.returnPressed.connect(self.create)
        self.things.clicked.connect(self.create)

        # When esc pressed, close
        self.input.cancelled.connect(self.close)

        # Up and down arrow handling
        self.input.pressed_arrow.connect(self.move_selection)

        self._resize_list_to_contents()

        self.adjustSize()

    def _resize_list_to_contents(self):
        """Set list height to always show num_items rows, giving a fixed popup size."""
        num_rows = self.things_model.num_items

        row_h = self.things.sizeHintForRow(0)
        if row_h <= 0:
            row_h = 20  # fallback row height in pixels

        try:
            fw = self.things.frameWidth()
        except Exception:
            fw = 0

        total_h = row_h * num_rows + self.things.spacing() * max(0, num_rows - 1) + 2 * fw
        self.things.setFixedHeight(total_h)

    def under_cursor(self):
        def clamp(val, mi, ma):
            return max(min(val, ma), mi)

        # Get cursor position, and screen dimensions on active screen
        cursor = QtGui.QCursor().pos()
        screen_obj = None
        if hasattr(QtWidgets.QApplication, 'screenAt'):
            screen_obj = QtWidgets.QApplication.screenAt(cursor)
        if screen_obj is None:
            screen_obj = self.screen()
        screen = screen_obj.geometry()

        # Get window position so cursor is just over text input
        xpos = cursor.x() - (self.width() / 2)
        ypos = cursor.y() - 13

        # Clamp window location to prevent it going offscreen
        xpos = clamp(xpos, screen.left(), screen.right() - self.width())
        ypos = clamp(ypos, screen.top(), screen.bottom() - (self.height() - 13))

        # Move window
        self.move(xpos, ypos)

    def move_selection(self, where):
        if where not in ["first", "up", "down"]:
            raise ValueError("where should be either 'first', 'up', 'down', not %r" % (
                where))

        first = where == "first"
        up = where == "up"
        down = where == "down"

        if first:
            self.things.setCurrentIndex(self.things_model.index(0))
            return

        cur = self.things.currentIndex()
        if up:
            new = cur.row() - 1
            if new < 0:
                new = self.things_model.rowCount() - 1
        elif down:
            new = cur.row() + 1
            count = self.things_model.rowCount()
            if new > count - 1:
                new = 0

        self.things.setCurrentIndex(self.things_model.index(new))

    def event(self, event):
        """Close when window becomes inactive (click outside of window)"""
        if event.type() == QtCore.QEvent.WindowDeactivate:
            self.close()
            return True
        else:
            return super(TabTabTabWidget, self).event(event)

    def update(self, text):
        """On text change, selects first item and updates filter text"""
        self.things.setCurrentIndex(self.things_model.index(0))
        self.things_model.set_filter(text)

    def show(self):
        """Select all the text in the input (which persists between
        show()'s)

        Allows typing over previously created text, and [tab][tab] to
        create previously created node (instead of the most popular)
        """

        # Show the widget and focus the input *before* doing any heavy work.
        # Reloading weights from disk and re-walking the host application's
        # menus can take 100-400ms; if those run synchronously here, queued
        # KeyPress events arrive before the line-edit is ready and the user's
        # first character or two get lost (issue #3). Deferring via
        # singleShot(0) lets Qt drain pending input events into the now-
        # focused line-edit before the refresh blocks the GUI thread again.
        #
        # The popup's previous-open items remain in NodeModel between
        # close and re-open. Now that NodeModel emits row ops instead of
        # modelReset, the deferred refreshes morph that retained state
        # incrementally — no blank flash between show() and the first
        # tick, and no jump when the second tick fires.
        self.input.selectAll()
        super(TabTabTabWidget, self).show()
        self.input.setFocus()

        QtCore.QTimer.singleShot(0, self._refresh_after_show)

    def _refresh_after_show(self):
        """Cheap refresh: reload weights and render whatever the plugin's
        cache currently has, so the user has results to look at and can
        type immediately.

        Runs on the next event-loop tick after show() so the user's first
        keystrokes land in the line-edit even though this work is slow.

        Schedules _refresh_fresh on the following tick to bound staleness:
        the cache may be one step behind reality (a deep submenu install
        the plugin's fingerprint can't sample, or a default-node-colour
        preference edit), and waiting until close to refresh would leave
        the user staring at stale data for the entire open session.
        """
        # Load the weights everytime the panel is shown, to prevent
        # overwritting weights from other instances
        self.weights.load()

        # Refresh items from the plugin so additions/removals are reflected.
        # NodeModel emits row ops, so this pass quietly morphs the retained
        # previous-open state into current results without blanking the view.
        self.things_model.refresh_items(self.plugin.get_items())

        # Restore selection to the first item; row ops preserve selection
        # in general, but a previously-selected row may no longer exist.
        self.move_selection(where="first")

        # Schedule the expensive freshness pass after focus and the cheap
        # render are settled. The user can already type; this catches any
        # staleness the plugin's own cache check missed.
        QtCore.QTimer.singleShot(0, self._refresh_fresh)

    def _refresh_fresh(self):
        """Expensive refresh: force a full re-walk of the plugin's items,
        bypassing whatever cache the cheap path used.

        Runs one tick after _refresh_after_show. Bounds staleness to a
        brief moment after open instead of an entire open/close cycle,
        at the cost of a possible slight typing hitch while the walk
        runs. No-op if the user already closed the popup before this
        fires — the next open will repeat the same two-stage refresh.

        NodeModel emits row ops rather than modelReset, so this pass is
        visually quiet when nothing changed: only rows that genuinely
        differ get touched.
        """
        if not self.isVisible():
            return
        self.plugin.invalidate_cache()
        self.things_model.refresh_items(self.plugin.get_items())
        self.move_selection(where="first")

    def close(self):
        """Save weights and close the dialog."""
        self.weights.save()
        super(TabTabTabWidget, self).close()

    def create(self):
        # Get selected item
        selected = self.things.selectedIndexes()
        if len(selected) == 0:
            return

        thing = self.things_model.getorig(selected)

        # Store the full UI name of the created node, so it is the
        # active node on the next [tab]. Prefix it with space,
        # to disable substring matching
        if thing['text'].startswith(" "):
            prev_string = thing['text']
        else:
            prev_string = " %s" % thing['text']

        self.input.setText(prev_string)

        # Invoke item, increment weight and close
        self.plugin.invoke(thing)
        self.weights.increment(thing['menupath'])
        self.close()


_tabtabtab_instance = None


_NUKE_MAIN_WINDOW_CLASSNAME = "Foundry::UI::DockMainWindow"


def _find_nuke_main_window():
    """Return Nuke's canonical main window (a QMainWindow), or None.

    Nuke historically has multiple top-level QMainWindow instances —
    floating panels, the Hiero/Studio bin/timeline, etc. Picking "the
    first QMainWindow from topLevelWidgets()" is order-dependent and
    can land us on a panel that the user later closes, taking our
    popup with it. Identifying the main window canonically:

      1. Match by Qt metaobject class name. Nuke's main window has a
         stable className of "Foundry::UI::DockMainWindow" across
         Nuke 11+; floating panels and other QMainWindows do not.
      2. Fallback: any parentless QMainWindow whose title contains
         " - Nuke" (matches "<file> - Nuke 14.0v5", "<file> - NukeX ...",
         "<file> - NukeStudio ...", etc.) — covers modified Nuke
         distributions or future class-name changes while still
         excluding bare panels.
      3. Otherwise None — better to be parentless than to grab a
         floating panel and have the popup disappear when it closes.

    Used as the Qt parent of the popup so its lifetime is owned by the
    host. The host destroys child widgets in defined order during
    shutdown, which avoids the dangling-wrapper segfault that the old
    weakref-only pattern (dbr/tabtabtab-nuke#4) was working around.
    """
    app = QtWidgets.QApplication.instance()
    if app is None:
        return None

    main_windows = [
        widget for widget in app.topLevelWidgets()
        if isinstance(widget, QtWidgets.QMainWindow)
    ]

    for widget in main_windows:
        if widget.metaObject().className() == _NUKE_MAIN_WINDOW_CLASSNAME:
            return widget

    for widget in main_windows:
        if widget.parent() is not None:
            continue
        title = widget.windowTitle() or ""
        if " - Nuke" in title:
            return widget

    return None


def _clear_tabtabtab_instance(*_args):
    global _tabtabtab_instance
    _tabtabtab_instance = None


# Retry budget for preload-only re-parenting. Plugin-load typically runs
# before Nuke's main window is registered in topLevelWidgets(), but the
# main window appears within a second or two; ~10s of retries is enough
# without spinning indefinitely if something genuinely went wrong.
_REPARENT_RETRY_INTERVAL_MS = 500
_REPARENT_RETRY_MAX_ATTEMPTS = 20


def _try_reparent_preloaded(widget, attempts_remaining):
    """Re-parent a parentless preloaded `widget` to Nuke's main window;
    retry on a timer if the main window isn't in topLevelWidgets() yet.

    Used from preload() to recover when preload runs before the main
    window has been created. Without this, a session in which the user
    never invokes the popup leaves the cached instance parentless for
    the rest of the session — silently losing the parent-owned lifetime
    that prevents the dbr/tabtabtab-nuke#4 segfault on host shutdown.

    Bails out (no further retries) if the widget has been parented in
    the meantime (e.g., by launch()'s recovery path), or if the widget
    has become visible — at that point launch() owns recovery and a
    re-parent here would disrupt the user's open popup.
    """
    try:
        if widget.parent() is not None:
            return
        if widget.isVisible():
            return
    except RuntimeError:
        return

    parent = _find_nuke_main_window()
    if parent is not None:
        widget.setParent(parent, Qt.Dialog | Qt.FramelessWindowHint)
        return

    if attempts_remaining > 1:
        QtCore.QTimer.singleShot(
            _REPARENT_RETRY_INTERVAL_MS,
            lambda: _try_reparent_preloaded(widget, attempts_remaining - 1),
        )


def _create_tabtabtab_widget(plugin, space_mode_order):
    parent = _find_nuke_main_window()
    # Qt.Dialog keeps the widget a top-level window even with a parent set.
    # Without it, setWindowFlags(FramelessWindowHint) drops the dialog type
    # and Qt treats the widget as a child of the parent — which puts it in
    # the parent's z-stack (so the DAG can cover it) and stops it from
    # receiving WindowDeactivate (so click-outside no longer closes it).
    widget = TabTabTabWidget(
        plugin,
        parent=parent,
        winflags=Qt.Dialog | Qt.FramelessWindowHint,
        space_mode_order=space_mode_order,
    )
    widget.destroyed.connect(_clear_tabtabtab_instance)
    return widget


def launch(plugin, space_mode_order=None):
    global _tabtabtab_instance

    if _tabtabtab_instance is not None:
        try:
            # Liveness probe before any attribute writes: parent() touches
            # the underlying C++ object and raises RuntimeError if the
            # wrapper is dangling, so the except below catches a dead
            # widget cleanly rather than silently mutating things_model.
            current_parent = _tabtabtab_instance.parent()

            # Recover from preload-before-main-window: if preload() ran
            # before Nuke's main window existed in topLevelWidgets(),
            # _find_nuke_main_window() returned None and the cached
            # instance is parentless — silently re-exposing the on-quit
            # segfault from dbr/tabtabtab-nuke#4. Re-parent now if the
            # main window has since appeared. setParent(parent, flags)
            # also re-applies the window flags, which is required: a
            # bare setParent on a top-level widget would demote it to a
            # child of the main window's z-stack.
            if current_parent is None:
                rediscovered_parent = _find_nuke_main_window()
                if rediscovered_parent is not None:
                    _tabtabtab_instance.setParent(
                        rediscovered_parent,
                        Qt.Dialog | Qt.FramelessWindowHint,
                    )

            if (space_mode_order is not None
                    and len(space_mode_order) == len(DEFAULT_SPACE_MODE_ORDER)
                    and all(m in VALID_MODES for m in space_mode_order)):
                _tabtabtab_instance.things_model._space_mode_order = list(space_mode_order)
            _tabtabtab_instance.under_cursor()
            _tabtabtab_instance.show()
            _tabtabtab_instance.raise_()
            return
        except RuntimeError:
            # Defensive: in normal operation the destroyed-signal handler
            # (_clear_tabtabtab_instance) nulls the global synchronously
            # when the C++ widget is destroyed, so we should never reach
            # this branch with a dangling wrapper. Kept in case a
            # destroyed connection was ever severed or never wired up.
            _tabtabtab_instance = None

    _tabtabtab_instance = _create_tabtabtab_widget(plugin, space_mode_order)
    _tabtabtab_instance.under_cursor()
    _tabtabtab_instance.show()
    _tabtabtab_instance.raise_()


def preload(plugin, space_mode_order=None):
    """Eagerly construct the popup widget so the first user invocation hits
    the warm reuse path inside launch().

    Idempotent: returns immediately if an instance already exists (either
    from a previous preload or because the user invoked the popup before
    the deferred preload ran).

    Construction is ~30-50ms (menu walk + initial NodeModel build). Running
    that at host-plugin-load time blocks startup and may also race with
    the host's own menu population, so prefer schedule_preload() which
    defers via QTimer.singleShot(0, ...).
    """
    global _tabtabtab_instance
    if _tabtabtab_instance is not None:
        return

    _tabtabtab_instance = _create_tabtabtab_widget(plugin, space_mode_order)

    # If the main window hadn't appeared yet, _create_tabtabtab_widget left
    # the instance parentless. Schedule background retries so a preload-only
    # session (user never invokes the popup) still ends up Qt-parented and
    # benefits from the host-shutdown lifetime guarantee.
    if _tabtabtab_instance.parent() is None:
        preloaded_widget = _tabtabtab_instance
        QtCore.QTimer.singleShot(
            _REPARENT_RETRY_INTERVAL_MS,
            lambda: _try_reparent_preloaded(preloaded_widget, _REPARENT_RETRY_MAX_ATTEMPTS),
        )


def schedule_preload(plugin, space_mode_order=None):
    """Defer preload() to the next event-loop tick.

    Use this from the host's plugin entry point. Deferring guarantees
    (a) that startup isn't blocked by widget construction and (b) that
    the host's own menu population is complete before we walk it.
    """
    QtCore.QTimer.singleShot(
        0,
        lambda: preload(plugin, space_mode_order=space_mode_order),
    )
