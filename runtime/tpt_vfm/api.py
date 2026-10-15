# -*- coding: utf-8 -*-
"""Revit access, selective override merging and transactional operations."""
import io
import json
from vfm_host import DB
from System.Collections.Generic import List
from .ordering import ordered_filters

try:
    text_type = unicode
except NameError:
    text_type = str


def eid(value):
    return int(value.Value)


def ids(values):
    return List[DB.ElementId](list(values))


def name(element):
    return DB.Element.Name.GetValue(element)


def filters(doc):
    return sorted(list(DB.FilteredElementCollector(doc).OfClass(DB.FilterElement)),
                  key=lambda e: name(e).lower())


def all_views(doc):
    return sorted(list(DB.FilteredElementCollector(doc).OfClass(DB.View)),
                  key=lambda e: (str(e.ViewType), name(e).lower()))


def supported_views(doc):
    result = []
    for view in all_views(doc):
        try:
            if view.AreGraphicsOverridesAllowed():
                view.GetOrderedFilters()
                result.append(view)
        except Exception:
            continue
    return result


def controlled_by_template(doc, view):
    if view.IsTemplate or eid(view.ViewTemplateId) == -1:
        return None
    template = doc.GetElement(view.ViewTemplateId)
    if template is None:
        return None
    pid = int(DB.BuiltInParameter.VIS_GRAPHICS_FILTERS)
    included = set(eid(x) for x in template.GetTemplateParameterIds())
    excluded = set(eid(x) for x in template.GetNonControlledTemplateParameterIds())
    if pid in included and pid not in excluded:
        return template
    return None


def ensure_writable(doc, view=None):
    if doc.IsReadOnly:
        raise ValueError('This document is read-only.')
    if view is not None:
        template = controlled_by_template(doc, view)
        if template is not None:
            raise ValueError('Filters are controlled by template "{0}". Select that template as the destination.'.format(name(template)))


def snapshot(view):
    order = list(view.GetOrderedFilters())
    data = {}
    for fid in order:
        data[eid(fid)] = (DB.OverrideGraphicSettings(view.GetFilterOverrides(fid)),
                          view.GetFilterVisibility(fid), view.GetIsFilterEnabled(fid))
    return order, data


# Property name, setter name. Include both foreground and background pattern
# visibility, which is independent of pattern colour and pattern id.
GROUPS = {
    'projection': [('ProjectionLineColor', 'SetProjectionLineColor'),
                   ('ProjectionLinePatternId', 'SetProjectionLinePatternId'),
                   ('ProjectionLineWeight', 'SetProjectionLineWeight')],
    'cut': [('CutLineColor', 'SetCutLineColor'),
            ('CutLinePatternId', 'SetCutLinePatternId'),
            ('CutLineWeight', 'SetCutLineWeight')],
    'surface': [('SurfaceForegroundPatternId', 'SetSurfaceForegroundPatternId'),
                ('SurfaceForegroundPatternColor', 'SetSurfaceForegroundPatternColor'),
                ('IsSurfaceForegroundPatternVisible', 'SetSurfaceForegroundPatternVisible'),
                ('SurfaceBackgroundPatternId', 'SetSurfaceBackgroundPatternId'),
                ('SurfaceBackgroundPatternColor', 'SetSurfaceBackgroundPatternColor'),
                ('IsSurfaceBackgroundPatternVisible', 'SetSurfaceBackgroundPatternVisible')],
    'cutpattern': [('CutForegroundPatternId', 'SetCutForegroundPatternId'),
                   ('CutForegroundPatternColor', 'SetCutForegroundPatternColor'),
                   ('IsCutForegroundPatternVisible', 'SetCutForegroundPatternVisible'),
                   ('CutBackgroundPatternId', 'SetCutBackgroundPatternId'),
                   ('CutBackgroundPatternColor', 'SetCutBackgroundPatternColor'),
                   ('IsCutBackgroundPatternVisible', 'SetCutBackgroundPatternVisible')],
    'transparency': [('Transparency', 'SetSurfaceTransparency')],
    'halftone': [('Halftone', 'SetHalftone')],
    'detail': [('DetailLevel', 'SetDetailLevel')]
}


def merge_overrides(source, destination, groups, map_id=None):
    merged = DB.OverrideGraphicSettings(destination)
    properties = dict((prop, setter) for pairs in GROUPS.values() for prop, setter in pairs)
    for group in groups:
        pairs = GROUPS.get(group, [(group, properties[group])] if group in properties else [])
        for prop, setter in pairs:
            value = getattr(source, prop)
            if map_id is not None and prop.endswith('Id'):
                value = map_id(value)
            getattr(merged, setter)(value)
    return merged


def set_order(view, desired, settings):
    """Remove/re-add only when order changes, then restore every filter state."""
    current = list(view.GetOrderedFilters())
    if [eid(x) for x in current] != [eid(x) for x in desired]:
        for fid in current:
            view.RemoveFilter(fid)
        for fid in desired:
            view.AddFilter(fid)
        for fid in desired:
            overrides, visible, enabled = settings[eid(fid)]
            view.SetFilterOverrides(fid, overrides)
            view.SetFilterVisibility(fid, visible)
            view.SetIsFilterEnabled(fid, enabled)


def plan_copy(doc, source, selected, destinations, mode, placement, position):
    result = []
    source_ids = set(eid(x) for x in source.GetOrderedFilters())
    if not selected:
        raise ValueError('Select at least one source filter.')
    if any(eid(x) not in source_ids for x in selected):
        raise ValueError('A selected filter is no longer applied to the source. Refresh the source.')
    for view in destinations:
        row = {'view': name(view), 'id': eid(view.Id), 'status': 'ready', 'note': ''}
        try:
            ensure_writable(doc, view)
            if view.Id == source.Id:
                raise ValueError('Source view is skipped.')
            before = [eid(x) for x in view.GetOrderedFilters()]
            use = [eid(x) for x in selected]
            missing = [x for x in use if x not in before]
            if mode == 'overrides':
                use = [x for x in use if x in before]
                row['note'] = '{0} absent filters skipped in overrides-only mode.'.format(len(missing)) if missing else ''
                after = before
                if not use:
                    raise ValueError('None of the selected filters exist in this destination.')
            else:
                after, row['note'] = ordered_filters(before, use, placement, position)
            row.update(before=before, after=after, selected=use,
                       added=len([x for x in after if x not in before]))
        except Exception as exc:
            row.update(status='skipped', note=str(exc))
        result.append(row)
    return result


class AbortErrors(DB.IFailuresPreprocessor):
    def PreprocessFailures(self, accessor):
        for failure in accessor.GetFailureMessages():
            if failure.GetSeverity() == DB.FailureSeverity.Error:
                return DB.FailureProcessingResult.ProceedWithRollBack
        return DB.FailureProcessingResult.Continue


def transaction(doc, title, action):
    tx = DB.Transaction(doc, title)
    tx.Start()
    options = tx.GetFailureHandlingOptions()
    options.SetFailuresPreprocessor(AbortErrors())
    options.SetClearAfterRollback(True)
    tx.SetFailureHandlingOptions(options)
    try:
        value = action()
        if tx.Commit() != DB.TransactionStatus.Committed:
            raise ValueError('Revit rolled back the operation.')
        return value
    except Exception:
        if tx.GetStatus() == DB.TransactionStatus.Started:
            tx.RollBack()
        raise


def copy_filters(doc, source, plan, mode, groups):
    _, source_data = snapshot(source)
    results = []
    group = DB.TransactionGroup(doc, 'TPT View Filter Manager - copy')
    group.Start()
    try:
        for item in plan:
            row = dict(item)
            if row['status'] != 'ready':
                results.append(row)
                continue
            view = doc.GetElement(DB.ElementId(row['id']))
            try:
                def apply():
                    ensure_writable(doc, view)
                    current, states = snapshot(view)
                    if [eid(x) for x in current] != row['before']:
                        raise ValueError('Destination changed after preview. Run preview again.')
                    for value in row['selected']:
                        fid = DB.ElementId(value)
                        if value not in states:
                            view.AddFilter(fid)
                            states[value] = (DB.OverrideGraphicSettings(), True, True)
                        if mode != 'filters':
                            ogs, visible, enabled = states[value]
                            src, srcvis, srcenabled = source_data[value]
                            ogs = merge_overrides(src, ogs, groups)
                            if 'visibility' in groups:
                                visible = srcvis
                            if 'enabled' in groups:
                                enabled = srcenabled
                            states[value] = (ogs, visible, enabled)
                            view.SetFilterOverrides(fid, ogs)
                            view.SetFilterVisibility(fid, visible)
                            view.SetIsFilterEnabled(fid, enabled)
                    set_order(view, [DB.ElementId(x) for x in row['after']], states)
                transaction(doc, 'Copy filters: ' + name(view), apply)
                row['status'] = 'completed'
            except Exception as exc:
                row.update(status='failed', note=str(exc))
            results.append(row)
        group.Assimilate()
    except Exception:
        if group.GetStatus() == DB.TransactionStatus.Started:
            group.RollBack()
        raise
    return results


def usage(doc):
    result = dict((eid(f.Id), []) for f in filters(doc))
    for view in supported_views(doc):
        for fid in view.GetOrderedFilters():
            result.setdefault(eid(fid), []).append(view)
    return result


def remove_from_views(doc, filter_ids, views):
    rows = []
    group = DB.TransactionGroup(doc, 'TPT View Filter Manager - remove')
    group.Start()
    try:
        for view in views:
            try:
                def remove():
                    ensure_writable(doc, view)
                    present = set(eid(x) for x in view.GetOrderedFilters())
                    count = 0
                    for fid in filter_ids:
                        if eid(fid) in present:
                            view.RemoveFilter(fid)
                            count += 1
                    return count
                count = transaction(doc, 'Remove filters: ' + name(view), remove)
                rows.append({'view': name(view), 'status': 'completed', 'note': '{0} removed'.format(count)})
            except Exception as exc:
                rows.append({'view': name(view), 'status': 'failed', 'note': str(exc)})
        group.Assimilate()
    except Exception:
        if group.GetStatus() == DB.TransactionStatus.Started:
            group.RollBack()
        raise
    return rows


def delete_unused(doc, filter_ids):
    ensure_writable(doc)
    used = usage(doc)
    chosen = [doc.GetElement(x) for x in filter_ids]
    if any(used.get(eid(x.Id)) for x in chosen):
        raise ValueError('A selected filter is used. Remove it from its views/templates first.')
    expected = set(eid(x.Id) for x in chosen)
    def delete():
        deleted = set(eid(x) for x in doc.Delete(ids([x.Id for x in chosen])))
        if deleted - expected:
            raise ValueError('Revit would delete dependent elements. The entire deletion was rolled back.')
    transaction(doc, 'TPT View Filter Manager - purge unused', delete)


def unique_name(doc, proposed):
    names = set(name(x).lower() for x in filters(doc))
    if proposed.lower() not in names:
        return proposed
    i = 2
    while '{0} ({1})'.format(proposed, i).lower() in names:
        i += 1
    return '{0} ({1})'.format(proposed, i)


def duplicate_filter(doc, source, proposed):
    ensure_writable(doc)
    def duplicate():
        if isinstance(source, DB.ParameterFilterElement):
            new = DB.ParameterFilterElement.Create(doc, proposed, source.GetCategories())
            ef = source.GetElementFilter()
            if ef is not None:
                new.SetElementFilter(ef)
            return new
        if isinstance(source, DB.SelectionFilterElement):
            new = DB.SelectionFilterElement.Create(doc, proposed)
            new.SetElementIds(source.GetElementIds())
            return new
        raise ValueError('Unsupported filter type.')
    return transaction(doc, 'TPT View Filter Manager - duplicate', duplicate)


def value_json(value):
    if isinstance(value, DB.ElementId):
        return eid(value)
    if isinstance(value, DB.Color):
        return [value.Red, value.Green, value.Blue] if value.IsValid else None
    if isinstance(value, (int, float, bool, text_type)):
        return value
    return str(value)


def override_json(ogs):
    return dict((prop, value_json(getattr(ogs, prop)))
                for group in GROUPS.values() for prop, _ in group)


def export_library(doc, path):
    from .rules import encode_filter
    usages = usage(doc)
    data = {'schema': 'tpt-vfm-library-1', 'project': doc.Title, 'filters': []}
    for f in filters(doc):
        record = {'name': name(f), 'id': eid(f.Id), 'type': f.GetType().Name,
                  'categories': [], 'rules': None, 'uses': []}
        if isinstance(f, DB.ParameterFilterElement):
            record['categories'] = [DB.Category.GetCategory(doc, x).Name for x in f.GetCategories()]
            record['rules'] = encode_filter(doc, f.GetElementFilter())
        else:
            record['element_ids'] = [eid(x) for x in f.GetElementIds()]
        for view in usages[eid(f.Id)]:
            ogs = view.GetFilterOverrides(f.Id)
            record['uses'].append({'view': name(view), 'view_id': eid(view.Id),
                                   'template': bool(view.IsTemplate),
                                   'order': [eid(x) for x in view.GetOrderedFilters()].index(eid(f.Id)) + 1,
                                   'visible': view.GetFilterVisibility(f.Id),
                                   'enabled': view.GetIsFilterEnabled(f.Id),
                                   'overrides': override_json(ogs)})
        data['filters'].append(record)
    if path.lower().endswith('.json'):
        with io.open(path, 'w', encoding='utf-8') as stream:
            stream.write(text_type(json.dumps(data, ensure_ascii=False, indent=2)))
    else:
        def field(value):
            text = text_type(value)
            # Prevent spreadsheet applications interpreting names as formulas.
            if text.startswith(('=', '+', '-', '@')):
                text = u"'" + text
            return u'"' + text.replace(u'"', u'""') + u'"'
        with io.open(path, 'w', encoding='utf-8-sig') as stream:
            stream.write(u'Filter,Type,Categories,View,Template,Order,Visible,Enabled,Rules,Overrides\n')
            for record in data['filters']:
                uses = record['uses'] or [{}]
                for use in uses:
                    values = [record['name'], record['type'], '; '.join(record['categories']),
                              use.get('view', ''), use.get('template', ''), use.get('order', ''),
                              use.get('visible', ''), use.get('enabled', ''),
                              json.dumps(record['rules'], ensure_ascii=False),
                              json.dumps(use.get('overrides', {}), ensure_ascii=False)]
                    stream.write(u','.join(field(x) for x in values) + u'\n')
    return len(data['filters'])


def batch_rename(doc, rows):
    """Validate a fresh inventory and atomically rename with temporary names."""
    import uuid
    from . import renaming
    ensure_writable(doc)
    def apply():
        elements = dict((eid(f.Id), f) for f in filters(doc))
        inventory = dict((key, name(f)) for key, f in elements.items())
        errors, changes = renaming.prepare(rows, inventory, DB.NamingUtils.IsValidName,
                                          DB.NamingUtils.CompareNames)
        if errors:
            raise ValueError('Batch rename blocked:\n' + '\n'.join(errors[key] for key in sorted(errors)))
        occupied = list(inventory.values()) + [row['proposed'] for row in changes]
        for row in changes:
            temporary = 'TPT_Rename_' + uuid.uuid4().hex
            while any(DB.NamingUtils.CompareNames(temporary, value) == 0 for value in occupied):
                temporary = 'TPT_Rename_' + uuid.uuid4().hex
            elements[row['id']].Name = temporary
            occupied.append(temporary)
        for row in changes:
            elements[row['id']].Name = row['proposed']
        return len(changes)
    return transaction(doc, 'TPT View Filter Manager - batch rename', apply)
