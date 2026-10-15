# -*- coding: utf-8 -*-
import copy
import io
import json
import os
import traceback
from vfm_host import DB, forms, revit
from System.Collections.ObjectModel import ObservableCollection
from System.Windows.Media import BrushConverter, VisualTreeHelper
from System.Windows.Controls import ListBox, TreeView
from System.Windows.Input import Keyboard, ModifierKeys
from System import Object
from . import api, rules, transfer, selection, renaming, __version__

TITLE = 'View Filter Manager'
KINDS = ['Views / templates', 'Views only', 'Templates only']
PLACEMENTS = ['Stack selected at end', 'Keep position of common filters', 'Start at position']
PLACEMENT_KEYS = ['stacked', 'anchors', 'position']
CONFLICTS = ['Skip existing names', 'Reuse identical filters; skip templates', 'Create renamed copies']
CONFLICT_KEYS = ['skip', 'reuse', 'rename']
OVERRIDES = [
 ('visibility', 'Visibility'), ('ProjectionLineWeight', 'Projection Line Weight'),
 ('ProjectionLineColor', 'Projection Line Color'), ('ProjectionLinePatternId', 'Projection Line Pattern'),
 ('IsSurfaceForegroundPatternVisible', 'Projection Foreground Fill Visible'),
 ('SurfaceForegroundPatternColor', 'Projection Foreground Fill Color'),
 ('SurfaceForegroundPatternId', 'Projection Foreground Fill Pattern'),
 ('Transparency', 'Surface Transparency'), ('CutLineWeight', 'Cut Line Weight'),
 ('CutLineColor', 'Cut Line Color'), ('CutLinePatternId', 'Cut Line Pattern'),
 ('IsCutForegroundPatternVisible', 'Cut Foreground Fill Visible'),
 ('CutForegroundPatternColor', 'Cut Foreground Fill Color'), ('CutForegroundPatternId', 'Cut Foreground Fill Pattern'),
 ('Halftone', 'Halftone'), ('IsSurfaceBackgroundPatternVisible', 'Projection Background Fill Visible'),
 ('SurfaceBackgroundPatternColor', 'Projection Background Fill Color'),
 ('SurfaceBackgroundPatternId', 'Projection Background Fill Pattern'),
 ('IsCutBackgroundPatternVisible', 'Cut Background Fill Visible'),
 ('CutBackgroundPatternColor', 'Cut Background Fill Color'), ('CutBackgroundPatternId', 'Cut Background Fill Pattern'),
 ('DetailLevel', 'Detail Level'), ('enabled', 'Enable Filter')]

class Row(object):
    def __init__(self, value, label): self.Value, self.Label = value, label

def value_key(value):
    if hasattr(value, 'Id'): return api.eid(value.Id)
    if hasattr(value, 'GetHashCode'): return value.GetHashCode()
    return str(value)

class CheckNode(selection.TreeItem, forms.Reactive):
    def __init__(self, label, value=None, role=None, changed=None):
        selection.TreeItem.__init__(self, label, value, role, self.OnPropertyChanged, changed)
        self.Background = BrushConverter().ConvertFromString('Transparent')

def chosen(control):
    if hasattr(control, 'SelectedItems'):
        return [x.Value for x in control.SelectedItems if getattr(x.Value, 'IsValidObject', True)]
    return [x for x in selection.checked(control.Items, key=value_key) if getattr(x, 'IsValidObject', True)]

def select_values(control, values, key=value_key):
    keys = set(key(x) for x in values)
    if hasattr(control, 'SelectedItems'):
        control.UnselectAll()
        for item in control.Items:
            if key(item.Value) in keys: control.SelectedItems.Add(item)
    else:
        for node in selection.walk(control.Items):
            if node.Value is not None and key(node.Value) in keys: node.IsChecked = True

def checked_filters(control):
    values = chosen(control)
    if any(not isinstance(x, DB.FilterElement) for x in values):
        raise ValueError('Switch the explorer to project filters and check filters for this action.')
    return values

def single(control):
    values = checked_filters(control)
    if len(values) != 1: raise ValueError('Check exactly one filter for this action.')
    return values[0]

def confirm(message): return forms.alert(message, title=TITLE, yes=True, no=True)

def guard(action):
    def wrapped(self, sender=None, args=None):
        try: return action(self, sender, args)
        except Exception as exc:
            self.last_error = traceback.format_exc()
            forms.alert(str(exc), title=TITLE)
    return wrapped

def tree_check(control, value):
    for node in control.Items: node.IsChecked = value

def tree_expand(control, value):
    for node in selection.walk(control.Items): node.IsExpanded = value

def view_groups(parent, views, owner, role='view', filter_id=None, details=False):
    for is_template, label in ((False, 'Views'), (True, 'View Templates')):
        subset = [v for v in views if bool(v.IsTemplate) == is_template]
        if not subset: continue
        branch = parent.add(CheckNode(label, changed=owner.update_counts))
        branch.IsExpanded = True
        for typ in sorted(set(str(v.ViewType) for v in subset)):
            group = branch.add(CheckNode(typ, changed=owner.update_counts))
            group.IsExpanded = True
            for view in [v for v in subset if str(v.ViewType) == typ]:
                label = api.name(view)
                controlled = api.controlled_by_template(view.Document, view)
                if controlled: label += ' [VT: ' + api.name(controlled) + ']'
                node = group.add(CheckNode(label, view if role == 'view' else None, role, owner.update_counts))
                node.FilterId = filter_id
                if details:
                    for fid in view.GetOrderedFilters(): node.add(CheckNode(api.name(view.Document.GetElement(fid)), changed=owner.update_counts))

def checkbox_range_click(window, sender, args):
    control = sender
    while control is not None and not isinstance(control, (ListBox, TreeView)):
        control = VisualTreeHelper.GetParent(control)
    if control is None:
        return
    item = sender.DataContext
    anchors = getattr(window, '_check_anchors', None)
    if anchors is None:
        anchors = window._check_anchors = {}
    key = control.GetHashCode()
    shift = bool(Keyboard.Modifiers & ModifierKeys.Shift)
    items = list(selection.visible(control.Items)) if isinstance(control, TreeView) else list(control.Items)
    targets = selection.click_targets(items, item, anchors.get(key), shift)
    if isinstance(control, TreeView):
        value = True if shift else item.IsChecked is not True
        for target in targets:
            target.IsChecked = value
    else:
        value = True if shift else not control.SelectedItems.Contains(item)
        for target in targets:
            if value and not control.SelectedItems.Contains(target):
                control.SelectedItems.Add(target)
            elif not value and control.SelectedItems.Contains(target):
                control.SelectedItems.Remove(target)
    if not shift or key not in anchors or not any(x is anchors[key] for x in items):
        anchors[key] = item
    args.Handled = True


class ManagerWindow(forms.WPFWindow):
    def check_mouse_down(self, sender, args): checkbox_range_click(self, sender, args)

    def __init__(self, bundle):
        self._loading = True
        self.bundle, self.doc = bundle, revit.doc
        self.last_error = self.last_report = ''
        self._filter_order, self._imported_names = [], []
        self._library_scope, self._types_initialized = 0, False
        forms.WPFWindow.__init__(self, os.path.join(bundle, 'manager.xaml'))
        self.Title = TITLE
        self.source_kind.ItemsSource = self.dest_kind.ItemsSource = KINDS
        self.source_kind.SelectedIndex = self.dest_kind.SelectedIndex = 0
        self.placement.ItemsSource = PLACEMENTS
        self.placement.SelectedIndex = 1
        self.override_options.ItemsSource = [Row(key, label) for key, label in OVERRIDES]
        self.override_options.SelectAll()
        self._loading = False
        self.refresh()

    def refresh(self):
        old_source = self.source_views.SelectedItem.Value if self.source_views.SelectedItem else None
        old_types = chosen(self.view_types)
        old_source_filters, old_dest = chosen(self.source_filters), chosen(self.dest_views)
        self._loading = True
        self._views, self._filters, self._usage = api.supported_views(self.doc), api.filters(self.doc), api.usage(self.doc)
        types = sorted(set(str(v.ViewType) for v in self._views))
        self.view_types.ItemsSource = [Row(t, '{0} ({1})'.format(t, len([v for v in self._views if str(v.ViewType) == t]))) for t in types]
        if self._types_initialized: select_values(self.view_types, old_types)
        else: self.view_types.SelectAll()
        self._types_initialized = True
        self._loading = False
        self.fill_sources(old_source)
        select_values(self.source_filters, old_source_filters)
        self.fill_destinations(old_dest)
        self.fill_library()
        self.status_label.Text = self.doc.Title + ' | Check source filters, override properties and destination views, then Copy.'
        self.update_counts()

    def matching_views(self, kind, search):
        scope, types, query = kind.SelectedIndex, set(chosen(self.view_types)), search.Text.strip().lower()
        return [v for v in self._views if str(v.ViewType) in types and query in api.name(v).lower()
                and (scope == 0 or (scope == 1 and not v.IsTemplate) or (scope == 2 and v.IsTemplate))]

    def fill_sources(self, preferred=None):
        self._loading = True
        rows = [self.view_row(v) for v in self.matching_views(self.source_kind, self.source_search)]
        self.source_views.ItemsSource = rows
        target = preferred or self.doc.ActiveView
        self.source_views.SelectedIndex = next((i for i, row in enumerate(rows) if row.Value.Id == target.Id), 0 if rows else -1)
        self._loading = False
        self.load_source()

    def load_source(self):
        row = self.source_views.SelectedItem
        source = row.Value if row else None
        self._source_effective = (api.controlled_by_template(self.doc, source) or source) if source else None
        self._filter_order = list(self._source_effective.GetOrderedFilters()) if self._source_effective else []
        self.apply_sort()
        self.fill_source_filters()
        self.fill_destinations()

    def apply_sort(self):
        if self.sort_alpha.IsChecked:
            self._filter_order.sort(key=lambda x: api.name(self.doc.GetElement(x)).lower())
        elif self.sort_imported.IsChecked and self._imported_names:
            lookup = dict((api.name(self.doc.GetElement(x)), x) for x in self._filter_order)
            front = [lookup[n] for n in self._imported_names if n in lookup]
            self._filter_order = front + [x for x in self._filter_order if x not in front]

    def fill_source_filters(self):
        selected = chosen(self.source_filters)
        self._loading = True
        self.source_filters.ItemsSource = [Row(self.doc.GetElement(fid), api.name(self.doc.GetElement(fid))) for fid in self._filter_order]
        select_values(self.source_filters, selected)
        self._loading = False
        self.update_counts()

    def fill_destinations(self, preferred=None):
        selected = preferred if preferred is not None else chosen(self.dest_views)
        old_pairs = set((getattr(n, 'FilterId', None), value_key(n.Value)) for n in selection.walk(self.dest_views.Items)
                        if n.Value is not None and n.IsChecked is True)
        had_filter_tree = any(getattr(n, 'FilterId', None) is not None for n in selection.walk(self.dest_views.Items))
        views = self.matching_views(self.dest_kind, self.dest_search)
        self._loading = True
        roots = []
        if self.dest_by_filter.IsChecked:
            selected_ids = set(api.eid(f.Id) for f in chosen(self.source_filters))
            for fid in self._filter_order:
                if selected_ids and api.eid(fid) not in selected_ids: continue
                root = CheckNode(api.name(self.doc.GetElement(fid)), changed=self.update_counts)
                root.IsExpanded = True
                # Include eligible views without this filter too, so filters-only
                # and both modes can add missing source filters through this tree.
                view_groups(root, views, self, filter_id=api.eid(fid))
                roots.append(root)
        else:
            root = CheckNode('Views / View Templates', changed=self.update_counts)
            root.IsExpanded = True
            view_groups(root, views, self, details=True)
            roots.append(root)
        self.dest_views.ItemsSource = roots
        if preferred is None and self.dest_by_filter.IsChecked and had_filter_tree:
            for node in selection.walk(self.dest_views.Items):
                if node.Value is not None and (getattr(node, 'FilterId', None), value_key(node.Value)) in old_pairs:
                    node.IsChecked = True
        else:
            select_values(self.dest_views, selected)
        self._loading = False
        self.update_counts()

    def fill_library(self):
        selected, query = chosen(self.library_filters), self.library_search.Text.strip().lower()
        self._loading = True
        root = CheckNode('Project Parameters' if self.explore_parameters.IsChecked else 'Filters', changed=self.update_counts)
        root.IsExpanded = True
        if self.explore_parameters.IsChecked:
            self.explorer_border.BorderBrush = BrushConverter().ConvertFromString('#E0D800')
            for pe in DB.FilteredElementCollector(self.doc).OfClass(DB.ParameterElement):
                definition = pe.GetDefinition()
                binding = self.doc.ParameterBindings.get_Item(definition)
                if binding is None or query not in definition.Name.lower(): continue
                node = root.add(CheckNode(definition.Name, pe, 'parameter', self.update_counts))
                node.add(CheckNode(binding.GetType().Name))
                cats = node.add(CheckNode('Categories'))
                for cat in sorted(list(binding.Categories), key=lambda x: x.Name.lower()): cats.add(CheckNode(cat.Name))
        else:
            self.explorer_border.BorderBrush = BrushConverter().ConvertFromString('Transparent')
            view_ids = set(api.eid(v.Id) for v in self._views if str(v.ViewType) in set(chosen(self.view_types)))
            for f in self._filters:
                uses = [v for v in self._usage.get(api.eid(f.Id), []) if api.eid(v.Id) in view_ids]
                if query not in api.name(f).lower() or (self._library_scope == 1 and self._usage.get(api.eid(f.Id))) or (self._library_scope == 2 and not (isinstance(f, DB.ParameterFilterElement) and f.GetElementFilter() is None)): continue
                node = root.add(CheckNode(api.name(f), f, 'filter', self.update_counts))
                if uses: node.Background = BrushConverter().ConvertFromString('#D8F1D0')
                if isinstance(f, DB.ParameterFilterElement):
                    cats = node.add(CheckNode('Categories'))
                    for cid in f.GetCategories(): cats.add(CheckNode(DB.Category.GetCategory(self.doc, cid).Name))
                view_groups(node, uses, self, role='info')
        self.library_filters.ItemsSource = [root]
        select_values(self.library_filters, selected)
        self._loading = False
        self.update_counts()

    def update_counts(self):
        if self._loading: return
        self.source_count.Text = 'Checked {0}     Total {1}'.format(len(chosen(self.source_filters)), len(self.source_filters.Items))
        lib_total = len([n for n in selection.walk(self.library_filters.Items) if n.Value is not None])
        self.library_count.Text = 'Checked {0}     Total {1}'.format(len(chosen(self.library_filters)), lib_total)
        dest_total = len(set(value_key(n.Value) for n in selection.walk(self.dest_views.Items) if n.Value is not None))
        self.dest_count.Text = 'Checked {0}     Total {1}'.format(len(chosen(self.dest_views)), dest_total)

    def copy_inputs(self):
        if self._source_effective is None: raise ValueError('Select a source view/template.')
        selected_ids = set(api.eid(x.Id) for x in chosen(self.source_filters))
        selected = [x for x in self._filter_order if api.eid(x) in selected_ids]
        if not selected: raise ValueError('Check at least one source filter.')
        use_filters, use_overrides = bool(self.copy_filters_flag.IsChecked), bool(self.copy_overrides_flag.IsChecked)
        if not use_filters and not use_overrides: raise ValueError('Check Filters, Overrides, or both in section 6.')
        mode = 'both' if use_filters and use_overrides else 'filters' if use_filters else 'overrides'
        placement = PLACEMENT_KEYS[self.placement.SelectedIndex] if self.reorder.IsChecked else 'append'
        position = int(self.position.Text) if placement == 'position' else 1
        groups = chosen(self.override_options)
        if use_overrides and not groups: raise ValueError('Check override properties in section 3.')
        destinations = chosen(self.dest_views)
        if not destinations: raise ValueError('Check destination views/templates in section 4.')
        plan = []
        for view in destinations:
            use = selected
            if self.dest_by_filter.IsChecked:
                subset = set(n.FilterId for n in selection.walk(self.dest_views.Items)
                             if n.Value is not None and n.IsChecked is True and value_key(n.Value) == value_key(view))
                use = [fid for fid in selected if api.eid(fid) in subset]
            if use: plan.extend(api.plan_copy(self.doc, self._source_effective, use, [view], mode, placement, position))
        if not plan: raise ValueError('No destination is checked for a selected source filter.')
        return self._source_effective, plan, mode, groups

    def show_report(self, heading, rows):
        lines = [heading, '']
        for row in rows:
            lines.append('{0}: {1}'.format(row['status'].upper(), row['view']))
            if 'before' in row:
                labels = lambda values: ' > '.join(api.name(self.doc.GetElement(DB.ElementId(x))) for x in values)
                lines += ['  Before: ' + labels(row['before']), '  After: ' + labels(row['after'])]
            if row.get('note'): lines.append('  ' + row['note'])
            lines.append('')
        self.present_report('\n'.join(lines))

    def present_report(self, text):
        self.last_report = text
        window = ReportWindow(self.bundle, text)
        window.Owner = self
        window.ShowDialog()

    @guard
    def inspect_click(self, sender, args):
        if self.explore_parameters.IsChecked:
            values = chosen(self.library_filters)
            lines = []
            for pe in values:
                info = rules.parameter_info(self.doc, pe.Id)
                lines.append('{0}\n  {1}\n  GUID: {2}'.format(info['name'], info['datatype'], info.get('guid') or 'project parameter'))
            self.present_report('\n\n'.join(lines) or 'Check project parameters to inspect.')
        else:
            self.library_selection_changed(None, None)
            self.present_report(self.library_details.Text)

    @guard
    def coverage_click(self, sender, args):
        if self.explore_parameters.IsChecked:
            params = chosen(self.library_filters)
            selected = chosen(self.source_filters)
            lines = ['Checked parameters: {0}'.format(len(params)), 'Checked source filters: {0}'.format(len(selected)), '']
            for pe in params:
                binding = self.doc.ParameterBindings.get_Item(pe.GetDefinition())
                categories = set(cat.Name for cat in binding.Categories) if binding else set()
                needed = set(DB.Category.GetCategory(self.doc, c).Name for f in selected if isinstance(f, DB.ParameterFilterElement) for c in f.GetCategories())
                lines += ['PARAMETER: ' + pe.GetDefinition().Name, '---Missing category:', '    ' + ('\n    '.join(sorted(needed - categories)) or '(none)'), '']
        else:
            selected = checked_filters(self.library_filters) or chosen(self.source_filters)
            items = [(api.name(f), set(DB.Category.GetCategory(self.doc, c).Name for c in f.GetCategories())) for f in selected if isinstance(f, DB.ParameterFilterElement)]
            total, differences = selection.category_coverage(items)
            lines = ['Checked filters: {0}'.format(len(items)), "Checked filters' categories: {0}".format(total), '']
            for label, missing in differences:
                lines += ['FILTER: ' + label, '---Missing category:', '    ' + ('\n    '.join(missing) or '(none)'), '']
        self.present_report('\n'.join(lines))

    @guard
    def import_list_click(self, sender, args):
        path = forms.pick_file(file_ext='txt')
        if not path: return
        with io.open(path, 'r', encoding='utf-8-sig') as stream:
            names = [line.strip() for line in stream if line.strip()]
        self._imported_names = [n for i, n in enumerate(names) if n not in names[:i]]
        self._loading = True
        self.sort_imported.IsChecked = True
        self._loading = False
        self.apply_sort()
        self.fill_source_filters()
        lookup = dict((api.name(self.doc.GetElement(x)), self.doc.GetElement(x)) for x in self._filter_order)
        select_values(self.source_filters, [lookup[n] for n in self._imported_names if n in lookup])
        missing = [n for n in self._imported_names if n not in lookup]
        if missing: self.present_report('Imported list: unavailable source filters\n\n' + '\n'.join(missing))

    @guard
    def save_list_click(self, sender, args):
        selected = set(api.eid(f.Id) for f in chosen(self.source_filters))
        if not selected: raise ValueError('Check source filters first.')
        path = forms.save_file(file_ext='txt', default_name='Checked Filters.txt')
        if path:
            with io.open(path, 'w', encoding='utf-8') as stream:
                stream.write(api.text_type('\n'.join(api.name(self.doc.GetElement(x)) for x in self._filter_order if api.eid(x) in selected)))

    @guard
    def save_preset_click(self, sender, args):
        source_selection = set(api.eid(f.Id) for f in chosen(self.source_filters))
        data = {'schema': 'tpt-vfm-preset-2', 'filters_flag': bool(self.copy_filters_flag.IsChecked),
                'overrides_flag': bool(self.copy_overrides_flag.IsChecked), 'reorder': bool(self.reorder.IsChecked),
                'placement': self.placement.SelectedIndex, 'position': self.position.Text,
                'properties': chosen(self.override_options), 'filters': [api.name(self.doc.GetElement(x)) for x in self._filter_order if api.eid(x) in source_selection],
                'source_uid': self._source_effective.UniqueId if self._source_effective else None,
                'destinations': [v.UniqueId for v in chosen(self.dest_views)],
                'filter_destinations': bool(self.dest_by_filter.IsChecked),
                'pairs': [(api.name(self.doc.GetElement(DB.ElementId(n.FilterId))), n.Value.UniqueId)
                          for n in selection.walk(self.dest_views.Items) if n.Value is not None and n.IsChecked is True and getattr(n, 'FilterId', None) is not None]}
        path = forms.save_file(file_ext='json', default_name='ViewFilterManager-preset.json')
        if path:
            with io.open(path, 'w', encoding='utf-8') as stream: stream.write(api.text_type(json.dumps(data, ensure_ascii=False, indent=2)))

    @guard
    def load_preset_click(self, sender, args):
        path = forms.pick_file(file_ext='json')
        if not path: return
        with io.open(path, 'r', encoding='utf-8-sig') as stream: data = json.load(stream)
        if data.get('schema') == 'tpt-vfm-preset-1':
            old = data
            data = dict(old, schema='tpt-vfm-preset-2', filters_flag=old['mode'] in (0, 1),
                        overrides_flag=old['mode'] in (0, 2), reorder=old['placement'] != 0,
                        placement={0: 0, 1: 0, 2: 2, 3: 1}[old['placement']],
                        properties=[prop for group in old['groups'] for prop in
                                    ([group] if group in ('visibility', 'enabled') else [p for p, _ in api.GROUPS.get(group, [])])])
        if data.get('schema') != 'tpt-vfm-preset-2': raise ValueError('This is not a View Filter Manager preset.')
        placement, position = int(data['placement']), int(data['position'])
        if placement not in range(len(PLACEMENTS)) or position < 1: raise ValueError('Invalid placement settings.')
        self.copy_filters_flag.IsChecked, self.copy_overrides_flag.IsChecked = data['filters_flag'], data['overrides_flag']
        self.reorder.IsChecked, self.placement.SelectedIndex, self.position.Text = data['reorder'], placement, str(position)
        select_values(self.override_options, data['properties'])
        self._imported_names = data['filters']
        self._loading = True
        self.sort_imported.IsChecked = True
        self.view_types.SelectAll()
        self.source_kind.SelectedIndex = self.dest_kind.SelectedIndex = 0
        self.dest_by_filter.IsChecked = bool(data.get('filter_destinations', False))
        self.dest_by_view.IsChecked = not bool(data.get('filter_destinations', False))
        self.source_search.Text = self.dest_search.Text = ''
        self._loading = False
        source = self.doc.GetElement(data['source_uid']) if data.get('source_uid') else None
        self.fill_sources(source)
        lookup = dict((api.name(self.doc.GetElement(x)), self.doc.GetElement(x)) for x in self._filter_order)
        select_values(self.source_filters, [lookup[n] for n in self._imported_names if n in lookup])
        self.fill_destinations([v for v in self._views if v.UniqueId in data['destinations']])
        if data.get('filter_destinations'):
            tree_check(self.dest_views, False)
            pairs = set(tuple(x) for x in data.get('pairs', []))
            for node in selection.walk(self.dest_views.Items):
                if node.Value is not None and (api.name(self.doc.GetElement(DB.ElementId(node.FilterId))), node.Value.UniqueId) in pairs:
                    node.IsChecked = True

    def move(self, direction):
        selected = set(api.eid(f.Id) for f in chosen(self.source_filters))
        indexes = range(len(self._filter_order)) if direction < 0 else reversed(range(len(self._filter_order)))
        for i in indexes:
            j = i + direction
            if api.eid(self._filter_order[i]) in selected and 0 <= j < len(self._filter_order) and api.eid(self._filter_order[j]) not in selected:
                self._filter_order[i], self._filter_order[j] = self._filter_order[j], self._filter_order[i]
        self._imported_names = [api.name(self.doc.GetElement(x)) for x in self._filter_order]
        self._loading = True
        self.sort_imported.IsChecked = True
        self._loading = False
        self.fill_source_filters()

    def types_changed(self, sender, args):
        if not self._loading:
            self.fill_sources()
            self.fill_destinations()
            self.fill_library()
    def types_all_click(self, sender, args): self.view_types.SelectAll()
    def types_none_click(self, sender, args): self.view_types.UnselectAll()
    def overrides_all_click(self, sender, args): self.override_options.SelectAll()
    def overrides_none_click(self, sender, args): self.override_options.UnselectAll()
    def source_all_click(self, sender, args): self.source_filters.SelectAll()
    def source_none_click(self, sender, args): self.source_filters.UnselectAll()
    def up_click(self, sender, args): self.move(-1)
    def down_click(self, sender, args): self.move(1)
    def source_scope_changed(self, sender, args):
        if not self._loading: self.fill_sources()
    def source_changed(self, sender, args):
        if not self._loading: self.load_source()
    def source_checks_changed(self, sender, args):
        if not self._loading:
            if self.dest_by_filter.IsChecked: self.fill_destinations()
            self.update_counts()
    def destination_mode_changed(self, sender, args):
        if not self._loading: self.fill_destinations()
    def explorer_mode_changed(self, sender, args):
        if not self._loading: self.fill_library()
    def explorer_search_changed(self, sender, args):
        if not self._loading: self.fill_library()
    def explorer_selection_changed(self, sender, args): self.update_counts()
    def sort_alpha_click(self, sender, args):
        if not self._loading: self.apply_sort(); self.fill_source_filters()
    def sort_vg_click(self, sender, args):
        if not self._loading: self.load_source()
    def sort_imported_click(self, sender, args):
        if not self._loading: self.apply_sort(); self.fill_source_filters()
    def dest_all_click(self, sender, args): tree_check(self.dest_views, True)
    def dest_none_click(self, sender, args): tree_check(self.dest_views, False)
    def dest_expand_click(self, sender, args): tree_expand(self.dest_views, True)
    def dest_collapse_click(self, sender, args): tree_expand(self.dest_views, False)
    def library_all_click(self, sender, args): tree_check(self.library_filters, True)
    def library_none_click(self, sender, args): tree_check(self.library_filters, False)
    def library_expand_click(self, sender, args): tree_expand(self.library_filters, True)
    def library_collapse_click(self, sender, args): tree_expand(self.library_filters, False)
    def explore_all_click(self, sender, args): self._library_scope = 0; self.explore_filters.IsChecked = True; self.fill_library()
    def explore_unused_click(self, sender, args): self._library_scope = 1; self.explore_filters.IsChecked = True; self.fill_library()
    def explore_empty_click(self, sender, args): self._library_scope = 2; self.explore_filters.IsChecked = True; self.fill_library()
    def close_click(self, sender, args): self.Close()
    @guard
    def refresh_click(self, sender, args): self.refresh()
    @guard
    def open_transfer_click(self, sender, args):
        window = TransferWindow(self.bundle, self)
        window.Owner = self
        window.ShowDialog()
        self.refresh()
    def last_report_click(self, sender, args): self.present_report(self.last_report or 'No report yet.')
    def help_click(self, sender, args):
        self.present_report('1. Choose view types and a source.\n2. Check source filters and choose their order.\n3. Check individual override properties.\n4. Check destination views/templates. Filter mode targets each source filter separately.\n5. Enable reordering and choose placement.\n6. Choose Filters, Overrides or both, preview and copy.\n\nExplorer: applied filters are green; project parameters use a yellow frame. Edit actions use checked explorer filters. Explore > Report missing categories compares each checked filter with the union of their categories.\n\nTransfer: check elements and multiple open destination projects. Each project has a separate Undo operation.')

    def view_row(self, view):
        template = api.controlled_by_template(self.doc, view)
        suffix = ' [controlled by: {0}]'.format(api.name(template)) if template is not None else ''
        return Row(view, '{0} | {1}{2}{3}'.format(api.name(view), str(view.ViewType),
                                               ' | template' if view.IsTemplate else '', suffix))

    @guard
    def preview_click(self, sender, args):
        source, plan, mode, groups = self.copy_inputs()
        self.show_report('Copy preview | ' + api.name(source) + ' | ' + mode + ' | properties: ' + ', '.join(groups), plan)

    @guard
    def copy_click(self, sender, args):
        source, plan, mode, groups = self.copy_inputs()
        self.show_report('Copy preview | ' + api.name(source) + ' | properties: ' + ', '.join(groups), plan)
        ready = len([x for x in plan if x['status'] == 'ready'])
        if not ready:
            raise ValueError('No editable destinations. See the preview report.')
        if confirm('Apply {0} to {1} destination(s)?\n\nSee the preview report for final filter order. Successful changes are one Undo operation.'.format(mode, ready)):
            result = api.copy_filters(self.doc, source, plan, mode, groups)
            self.refresh()
            self.show_report('Copy results | ' + api.name(source), result)

    @guard
    def library_selection_changed(self, sender, args):
        selected = checked_filters(self.library_filters)
        lines = []
        for f in selected:
            lines.append(api.name(f) + ' | ' + f.GetType().Name)
            if isinstance(f, DB.ParameterFilterElement):
                lines.append('Categories: ' + ', '.join(DB.Category.GetCategory(self.doc, x).Name for x in f.GetCategories()))
                try:
                    tree = rules.encode_filter(self.doc, f.GetElementFilter())
                    def walk(node, depth=0):
                        if node is None:
                            return ['No rules (categories only)']
                        out = ['  ' * depth + rules.describe(node)]
                        for child in node.get('children', []):
                            out.extend(walk(child, depth + 1))
                        return out
                    lines.extend(walk(tree))
                except Exception as exc:
                    lines.append('Rule inspection: ' + str(exc))
            else:
                lines.append('{0} selection members'.format(len(list(f.GetElementIds()))))
            views = self._usage.get(api.eid(f.Id), [])
            lines.append('Applied to {0} views/templates:'.format(len(views)))
            for v in views:
                lines.append('  ' + api.name(v) + (' [template]' if v.IsTemplate else ''))
            lines.append('')
        self.library_details.Text = '\n'.join(lines) if lines else 'Select filters to inspect their categories, rules and usage.'

    @guard
    def create_click(self, sender, args):
        editor = EditorWindow(self.bundle, self.doc, None)
        editor.Owner = self
        editor.ShowDialog()
        self.refresh()

    @guard
    def edit_click(self, sender, args):
        f = single(self.library_filters)
        if not isinstance(f, DB.ParameterFilterElement):
            raise ValueError('Use Edit selection members for a selection filter.')
        editor = EditorWindow(self.bundle, self.doc, f)
        editor.Owner = self
        editor.ShowDialog()
        self.refresh()

    @guard
    def batch_rename_click(self, sender, args):
        selected = [f for f in chosen(self.library_filters) if isinstance(f, DB.FilterElement)]
        selected_ids = set(api.eid(f.Id) for f in selected)
        dialog = RenameWindow(self.bundle, self.doc, selected_ids)
        dialog.Owner = self
        dialog.ShowDialog()
        if dialog.applied:
            self.refresh()
            select_values(self.library_filters, [f for f in self._filters if api.eid(f.Id) in selected_ids])
            self.status_label.Text = 'Renamed {0} filters. Revit Undo restores the batch.'.format(dialog.applied)

    @guard
    def rename_click(self, sender, args):
        f = single(self.library_filters)
        proposed = forms.ask_for_string(default=api.name(f), prompt='New filter name', title=TITLE)
        if proposed and proposed.strip():
            api.ensure_writable(self.doc)
            api.transaction(self.doc, 'View Filter Manager - rename', lambda: setattr(f, 'Name', proposed.strip()))
            self.refresh()

    @guard
    def duplicate_click(self, sender, args):
        f = single(self.library_filters)
        proposed = forms.ask_for_string(default=api.unique_name(self.doc, api.name(f) + ' Copy'), prompt='Duplicate filter name', title=TITLE)
        if proposed and proposed.strip():
            api.duplicate_filter(self.doc, f, proposed.strip())
            self.refresh()

    @guard
    def selection_click(self, sender, args):
        f = single(self.library_filters)
        if not isinstance(f, DB.SelectionFilterElement):
            raise ValueError('Select a selection filter.')
        current = list(f.GetElementIds())
        text = forms.ask_for_string(default=', '.join(str(api.eid(x)) for x in current),
                                    prompt='Element IDs, separated by commas. Leave blank to empty this selection filter.', title=TITLE)
        if text is None:
            return
        values = [DB.ElementId(int(x.strip())) for x in text.split(',') if x.strip()]
        if any(self.doc.GetElement(x) is None for x in values):
            raise ValueError('An entered element ID does not exist in this project.')
        api.ensure_writable(self.doc)
        api.transaction(self.doc, 'View Filter Manager - selection members', lambda: f.SetElementIds(api.ids(values)))
        self.refresh()

    @guard
    def remove_click(self, sender, args):
        selected = checked_filters(self.library_filters)
        if not selected:
            raise ValueError('Select filters to remove.')
        all_used = dict((api.eid(v.Id), v) for f in selected for v in self._usage.get(api.eid(f.Id), []))
        choices = [self.view_row(v) for v in sorted(all_used.values(), key=api.name)]
        if not choices:
            raise ValueError('These filters are not applied to any views/templates.')
        picked = forms.SelectFromList.show(choices, name_attr='Label', multiselect=True,
                                          title='Remove selected filters from these views/templates', button_name='Review removal')
        if picked and confirm('Remove {0} selected filter(s) from {1} view(s)/template(s)?\n\nDefinitions remain in the project. Editing templates affects all views using them.'.format(len(selected), len(picked))):
            rows = api.remove_from_views(self.doc, [f.Id for f in selected], [x.Value for x in picked])
            self.refresh()
            self.show_report('Removal results', rows)

    @guard
    def purge_click(self, sender, args):
        selected = checked_filters(self.library_filters)
        if not selected:
            raise ValueError('Select unused filters to purge.')
        fresh_usage = api.usage(self.doc)
        used = [api.name(f) for f in selected if fresh_usage.get(api.eid(f.Id))]
        if used:
            raise ValueError('These filters are used and cannot be purged:\n' + '\n'.join(used))
        if confirm('Delete these {0} unused filter definitions?\n\n{1}\n\nThis operation can be undone in Revit.'.format(len(selected), '\n'.join(api.name(f) for f in selected))):
            api.delete_unused(self.doc, [f.Id for f in selected])
            self.refresh()
            self.status_label.Text = '{0} unused filter definitions deleted.'.format(len(selected))

    def export(self, extension):
        path = forms.save_file(file_ext=extension, default_name='ViewFilterManager-filters.' + extension)
        if path:
            count = api.export_library(self.doc, path)
            self.status_label.Text = 'Exported {0} filters to {1}'.format(count, path)

    @guard
    def export_csv_click(self, sender, args):
        self.export('csv')

    @guard
    def export_json_click(self, sender, args):
        self.export('json')

    @guard
    def save_report_click(self, sender, args):
        path = forms.save_file(file_ext='txt', default_name='ViewFilterManager-report.txt')
        if path:
            with io.open(path, 'w', encoding='utf-8') as stream:
                stream.write(api.text_type(self.last_report + ('\n\nLast error details:\n' + self.last_error if self.last_error else '')))

class ReportWindow(forms.WPFWindow):
    def __init__(self, bundle, text):
        self.text = text
        forms.WPFWindow.__init__(self, os.path.join(bundle, 'report.xaml'))
        self.report_text.Text = text
    def close_click(self, sender, args): self.Close()
    def save_click(self, sender, args):
        path = forms.save_file(file_ext='txt', default_name='View Filter Manager - Report.txt')
        if path:
            with io.open(path, 'w', encoding='utf-8') as stream: stream.write(api.text_type(self.text))

class TransferWindow(forms.WPFWindow):
    def check_mouse_down(self, sender, args): checkbox_range_click(self, sender, args)

    def __init__(self, bundle, manager):
        self._loading = True
        self.bundle, self.manager, self.last_error = bundle, manager, ''
        forms.WPFWindow.__init__(self, os.path.join(bundle, 'transfer.xaml'))
        docs = [d for d in manager.doc.Application.Documents if not d.IsFamilyDocument and not d.IsLinked]
        self.docs = docs
        self.source_project.ItemsSource = [Row(d, d.Title) for d in docs]
        self.source_project.SelectedIndex = next((i for i, d in enumerate(docs) if d.Equals(manager.doc)), 0)
        self.conflict.ItemsSource = CONFLICTS
        self.conflict.SelectedIndex = 0
        self._loading = False
        self.fill()
    def update_counts(self): pass
    def fill(self):
        row = self.source_project.SelectedItem
        if row is None: return
        doc = row.Value
        roots = []
        filters = api.filters(doc)
        root = CheckNode('Filters ({0})'.format(len(filters)))
        root.IsExpanded = True
        for f in filters: root.add(CheckNode(api.name(f), f, 'element'))
        roots.append(root)
        templates = [v for v in api.supported_views(doc) if v.IsTemplate]
        root = CheckNode('View Templates ({0})'.format(len(templates)))
        root.IsExpanded = True
        for typ in sorted(set(str(v.ViewType) for v in templates)):
            branch = root.add(CheckNode(typ))
            branch.IsExpanded = True
            for template in [v for v in templates if str(v.ViewType) == typ]:
                node = branch.add(CheckNode(api.name(template), template, 'element'))
                for fid in template.GetOrderedFilters(): node.add(CheckNode(api.name(doc.GetElement(fid)), doc.GetElement(fid), 'element'))
        roots.append(root)
        self.elements.ItemsSource = roots
        self.projects.ItemsSource = [Row(d, d.Title) for d in self.docs if not d.Equals(doc)]
    def source_changed(self, sender, args):
        if not self._loading: self.fill()
    def inputs(self):
        source = self.source_project.SelectedItem.Value
        values, projects = chosen(self.elements), chosen(self.projects)
        if not values or not projects: raise ValueError('Check elements and at least one destination project.')
        policy = CONFLICT_KEYS[self.conflict.SelectedIndex]
        plans = [(d, transfer.preflight(source, d, values, policy)) for d in projects]
        return source, policy, plans
    def report(self, heading, plans):
        text = [heading, '']
        for doc, rows in plans:
            text += ['PROJECT: ' + doc.Title]
            for r in rows: text += ['{0}: {1}\n  {2}'.format(r['status'].upper(), r['view'], r.get('note', ''))]
            text.append('')
        content = '\n'.join(text)
        self.manager.last_report = content
        window = ReportWindow(self.bundle, content)
        window.Owner = self
        window.ShowDialog()
    @guard
    def preview_click(self, sender, args):
        source, policy, plans = self.inputs()
        self.report('Transfer preview | ' + source.Title, plans)
    @guard
    def transfer_click(self, sender, args):
        source, policy, plans = self.inputs()
        self.report('Transfer preview | ' + source.Title, plans)
        total = sum(len([r for r in rows if r['status'] == 'ready']) for _, rows in plans)
        if not total: raise ValueError('No transferable items. Review the report.')
        if confirm('Transfer {0} item/project pairs to {1} projects?\n\nComplete templates use native Revit copy; same-name dependent types use destination types. Each project has its own Undo operation.'.format(total, len(plans))):
            results = []
            for doc, rows in plans:
                try: results.append((doc, transfer.execute(source, doc, rows, policy)))
                except Exception as exc: results.append((doc, [{'view': doc.Title, 'status': 'failed', 'note': str(exc)}]))
            self.report('Transfer results', results)
    def all_click(self, sender, args): tree_check(self.elements, True)
    def none_click(self, sender, args): tree_check(self.elements, False)
    def expand_click(self, sender, args): tree_expand(self.elements, True)
    def collapse_click(self, sender, args): tree_expand(self.elements, False)
    def projects_all_click(self, sender, args): self.projects.SelectAll()
    def projects_none_click(self, sender, args): self.projects.UnselectAll()
    def close_click(self, sender, args): self.Close()


class RenameRow(forms.Reactive):
    def __init__(self, element, checked, changed):
        self.Id, self.OriginalName = api.eid(element.Id), api.name(element)
        self._proposed, self._checked = self.OriginalName, checked
        self.Status, self.StatusBrush = '', BrushConverter().ConvertFromString('#333333')
        self._changed = changed

    @property
    def IsChecked(self): return self._checked
    @IsChecked.setter
    def IsChecked(self, value):
        self._checked = bool(value)
        self.OnPropertyChanged('IsChecked')
        self._changed()

    @property
    def ProposedName(self): return self._proposed
    @ProposedName.setter
    def ProposedName(self, value):
        self._proposed = value or ''
        self.OnPropertyChanged('ProposedName')
        self._changed()

    def snapshot(self):
        return {'id': self.Id, 'original': self.OriginalName, 'proposed': self.ProposedName, 'checked': self.IsChecked}

    def status(self, text, invalid):
        self.Status = text
        self.StatusBrush = BrushConverter().ConvertFromString('#B00020' if invalid else '#333333')
        self.OnPropertyChanged('Status')
        self.OnPropertyChanged('StatusBrush')


class RenameWindow(forms.WPFWindow):
    def __init__(self, bundle, doc, selected_ids):
        self.doc, self.applied, self._loading, self._anchor = doc, 0, True, None
        elements = api.filters(doc)
        self.inventory = dict((api.eid(f.Id), api.name(f)) for f in elements)
        self.rows = [RenameRow(f, api.eid(f.Id) in selected_ids, self.update) for f in elements]
        forms.WPFWindow.__init__(self, os.path.join(bundle, 'rename.xaml'))
        self.rename_rows.ItemsSource = self.rows
        self._loading = False
        self.update()

    def update(self):
        if self._loading: return
        snapshots = [row.snapshot() for row in self.rows]
        errors, changes = renaming.prepare(snapshots, self.inventory, DB.NamingUtils.IsValidName, DB.NamingUtils.CompareNames)
        for row in self.rows:
            row.status(errors.get(row.Id, 'Ready' if row.ProposedName != row.OriginalName else 'Unchanged') if row.IsChecked else 'Not checked', row.Id in errors)
        count = len([r for r in self.rows if r.IsChecked])
        self.rename_count.Text = 'Checked {0} | Changed {1} | Invalid {2}'.format(count, len([r for r in self.rows if r.IsChecked and r.ProposedName != r.OriginalName]), len(errors))
        self.rename_apply.IsEnabled = bool(changes) and not errors

    def row_mouse_down(self, sender, args):
        row = sender.DataContext
        shift = bool(Keyboard.Modifiers & ModifierKeys.Shift)
        targets = selection.click_targets(self.rows, row, self._anchor, shift)
        self._loading = True
        try:
            value = True if shift else not row.IsChecked
            for target in targets: target.IsChecked = value
            if not shift or self._anchor is None: self._anchor = row
        finally:
            self._loading = False
        args.Handled = True
        self.update()

    @guard
    def preview_click(self, sender, args):
        self._loading = True
        try:
            for row in self.rows:
                if row.IsChecked:
                    row.ProposedName = renaming.transform(row.OriginalName, self.rename_find.Text, self.rename_replace.Text,
                                                        self.rename_prefix.Text, self.rename_suffix.Text, bool(self.rename_match_case.IsChecked), bool(self.rename_whole_words.IsChecked))
        finally:
            self._loading = False
        self.update()

    def set_checks(self, value):
        self._loading = True
        for row in self.rows: row.IsChecked = value
        self._loading = False
        self.update()
    def all_click(self, sender, args): self.set_checks(True)
    def none_click(self, sender, args): self.set_checks(False)
    def reset_click(self, sender, args):
        self._loading = True
        for row in self.rows: row.ProposedName = row.OriginalName
        for control in (self.rename_find, self.rename_replace, self.rename_prefix, self.rename_suffix): control.Text = ''
        self.rename_match_case.IsChecked = True
        self.rename_whole_words.IsChecked = True
        self._loading = False
        self.update()

    @guard
    def apply_click(self, sender, args):
        self.update()
        if not self.rename_apply.IsEnabled:
            raise ValueError('Resolve invalid names and check at least one changed row before applying.')
        self.applied = api.batch_rename(self.doc, [row.snapshot() for row in self.rows])
        self.Close()
    def cancel_click(self, sender, args): self.Close()


class RuleNode(object):
    def __init__(self, data):
        self.Data = data
        self.Label = rules.describe(data)
        self.Children = ObservableCollection[Object]()
        for child in data.get('children', []):
            self.Children.Add(RuleNode(child))


class EditorWindow(forms.WPFWindow):
    def __init__(self, bundle, doc, existing):
        self._loading = True
        self.doc, self.existing = doc, existing
        self.categories = list(existing.GetCategories()) if existing else []
        self.tree = copy.deepcopy(rules.encode_filter(doc, existing.GetElementFilter())) if existing else None
        forms.WPFWindow.__init__(self, os.path.join(bundle, 'editor.xaml'))
        self.filter_name.Text = api.name(existing) if existing else api.unique_name(doc, 'New filter')
        self.operators.ItemsSource = ['Equals', 'Does not equal', 'Contains', 'Begins with', 'Ends with',
                                     'Greater than', 'Greater or equal', 'Less than', 'Less or equal', 'Has value', 'Has no value']
        self.operators.SelectedIndex = 0
        self._loading = False
        self.update_categories()
        self.redraw()

    def redraw(self):
        self.rule_tree.ItemsSource = [RuleNode(self.tree)] if self.tree else []

    def update_categories(self):
        labels = [DB.Category.GetCategory(self.doc, x).Name for x in self.categories]
        self.categories_label.Text = 'Categories: ' + (', '.join(labels) or 'Choose at least one category')
        self._parameters = rules.common_parameters(self.doc, self.categories) if self.categories else []
        self.parameter_search_changed(None, None)

    @guard
    def categories_click(self, sender, args):
        categories = [DB.Category.GetCategory(self.doc, x) for x in DB.ParameterFilterUtilities.GetAllFilterableCategories()]
        categories = sorted([x for x in categories if x is not None], key=lambda x: x.Name.lower())
        selected_ids = set(api.eid(x) for x in self.categories)
        class CategoryOption(forms.TemplateListItem):
            @property
            def name(self): return self.item.Name
        choices = [CategoryOption(c, api.eid(c.Id) in selected_ids) for c in categories]
        result = forms.SelectFromList.show(choices, multiselect=True, title='Filter categories', button_name='Use categories')
        if result is not None:
            self.categories = [c.Id for c in result]
            self.update_categories()

    def parameter_search_changed(self, sender, args):
        if self._loading:
            return
        query = self.parameter_search.Text.strip().lower()
        options = [Row(p, '{0} [{1}]'.format(p['name'], p['storage'])) for p in self._parameters if query in p['name'].lower()]
        self.parameters.ItemsSource = options
        self.parameters.SelectedIndex = 0 if options else -1

    def parameter_changed(self, sender, args):
        if self._loading:
            return
        row = self.parameters.SelectedItem
        if row is None:
            self.value_hint.Text = 'Choose categories and a common filterable parameter.'
            return
        kind = row.Value['storage']
        hints = {'String': 'Enter text. Revit string comparisons ignore case.',
                 'Integer': 'Enter an integer. For Yes/No parameters use 1 or 0.',
                 'Double': 'Enter a value with project units when available. Otherwise use internal:<number> (feet for length).',
                 'ElementId': 'Enter the Revit element ID of a type, material, level or other referenced definition.'}
        self.value_hint.Text = hints.get(kind, 'Storage type unavailable.')

    def new_rule(self):
        row = self.parameters.SelectedItem
        if row is None:
            raise ValueError('Choose a common parameter first.')
        return rules.guided_rule(self.doc, row.Value, str(self.operators.SelectedItem), self.value.Text)

    def add(self, data):
        selected = self.rule_tree.SelectedItem
        if self.tree is None:
            self.tree = data
        elif selected and selected.Data['kind'] in ('and', 'or', 'parameters'):
            parent = selected.Data
            if parent['kind'] == 'parameters' and data['kind'] in ('and', 'or'):
                raise ValueError('Select an AND/OR group to add a nested group, or select the root rule to wrap it.')
            parent['children'].append(data)
        else:
            self.tree = {'kind': 'and', 'children': [self.tree, data]}
        self.redraw()

    @guard
    def add_rule_click(self, sender, args): self.add(self.new_rule())
    @guard
    def and_click(self, sender, args): self.add({'kind': 'and', 'children': []})
    @guard
    def or_click(self, sender, args): self.add({'kind': 'or', 'children': []})

    def replace_node(self, current, target, replacement):
        if current is target:
            return replacement
        if 'children' in current:
            current['children'] = [self.replace_node(child, target, replacement) for child in current['children']]
            current['children'] = [x for x in current['children'] if x is not None]
        return current

    @guard
    def replace_rule_click(self, sender, args):
        selected = self.rule_tree.SelectedItem
        if selected is None or selected.Data['kind'] in ('and', 'or', 'parameters'):
            raise ValueError('Select an individual rule to replace.')
        self.tree = self.replace_node(self.tree, selected.Data, self.new_rule())
        self.redraw()

    @guard
    def remove_node_click(self, sender, args):
        selected = self.rule_tree.SelectedItem
        if selected:
            self.tree = self.replace_node(self.tree, selected.Data, None)
            self.redraw()

    def clear_click(self, sender, args):
        if confirm('Clear all rules? The filter will match its categories only until you add new rules.'):
            self.tree = None
            self.redraw()

    @guard
    def save_click(self, sender, args):
        proposed = self.filter_name.Text.strip()
        if not proposed:
            raise ValueError('Enter a filter name.')
        if self.existing and api.usage(self.doc).get(api.eid(self.existing.Id)):
            if not confirm('Save the filter definition? This changes its rules in every view/template that uses it.'):
                return
        rules.save_filter(self.doc, self.existing, proposed, self.categories, self.tree)
        self.Close()

    def cancel_click(self, sender, args): self.Close()
