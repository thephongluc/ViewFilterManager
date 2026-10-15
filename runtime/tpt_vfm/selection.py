# -*- coding: utf-8 -*-
"""Checkbox tree state and category coverage, independent of Revit/WPF."""
class TreeItem(object):
    def __init__(self, label, value=None, role=None, notify=None, changed=None):
        self.Label, self.Value, self.Role = label, value, role
        self.Children = []
        self.Parent = None
        self._checked = False
        self._expanded = False
        self._notify, self._changed = notify, changed
        self.Background = 'Transparent'

    def add(self, child):
        child.Parent = self
        self.Children.append(child)
        return child

    def signal(self, prop):
        if self._notify:
            self._notify(prop)

    @property
    def IsChecked(self):
        return self._checked

    @IsChecked.setter
    def IsChecked(self, value):
        self.set_checked(bool(value))

    def set_checked(self, value, cascade=True, bubble=True):
        self._checked = bool(value)
        self.signal('IsChecked')
        if cascade:
            for child in self.Children:
                child.set_checked(value, True, False)
        if bubble and self.Parent:
            self.Parent.recompute()
        if bubble and self._changed:
            self._changed()

    def recompute(self):
        states = [child.IsChecked for child in self.Children]
        self._checked = True if all(x is True for x in states) else False if all(x is False for x in states) else None
        self.signal('IsChecked')
        if self.Parent:
            self.Parent.recompute()

    @property
    def IsExpanded(self):
        return self._expanded

    @IsExpanded.setter
    def IsExpanded(self, value):
        self._expanded = bool(value)
        self.signal('IsExpanded')


def walk(nodes):
    for node in nodes:
        yield node
        for child in walk(node.Children):
            yield child


def checked(nodes, role=None, key=None):
    result, seen = [], set()
    for node in walk(nodes):
        if node.IsChecked is not True or node.Value is None or (role and node.Role != role):
            continue
        identity = key(node.Value) if key else id(node.Value)
        if identity not in seen:
            result.append(node.Value)
            seen.add(identity)
    return result


def category_coverage(items):
    """items = [(filter name, set of category names)]. Compare against union."""
    universe = set(c for _, categories in items for c in categories)
    return len(universe), [(name, sorted(universe - set(categories))) for name, categories in items]


def visible(nodes):
    """Tree rows in display order; collapsed descendants are excluded."""
    for node in nodes:
        yield node
        if node.IsExpanded:
            for child in visible(node.Children):
                yield child


def click_targets(items, item, anchor=None, shift=False):
    """Inclusive range by identity, or the clicked row when anchor is stale."""
    index = next(i for i, value in enumerate(items) if value is item)
    start = next((i for i, value in enumerate(items) if value is anchor), index)
    if not shift:
        return [item]
    return items[min(start, index):max(start, index) + 1]
