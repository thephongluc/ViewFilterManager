# -*- coding: utf-8 -*-
"""Cross-project transfer with explicit conflicts and parameter mapping."""
import json
from vfm_host import DB
from . import api, rules


def fingerprint(element):
    if isinstance(element, DB.FillPatternElement):
        pattern = element.GetFillPattern()
        return (str(pattern.Target), bool(pattern.IsSolidFill),
                tuple((grid.Angle, grid.Offset, grid.Shift, grid.Origin.U, grid.Origin.V,
                       tuple(grid.GetSegments())) for grid in pattern.GetFillGrids()))
    if isinstance(element, DB.LinePatternElement):
        return tuple((str(x.Type), x.Length) for x in element.GetLinePattern().GetSegments())
    raise ValueError('Only fill and line pattern IDs are accepted as graphic dependencies.')


def pattern_mapper(source, destination, create=False):
    def resolve(fid):
        if api.eid(fid) < 0:
            return fid
        element = source.GetElement(fid)
        kind = element.GetType()
        expected = fingerprint(element)
        matches = [x for x in DB.FilteredElementCollector(destination).OfClass(kind)
                   if api.name(x) == api.name(element)]
        if matches:
            exact = [x for x in matches if fingerprint(x) == expected]
            if len(exact) == 1:
                return exact[0].Id
            raise ValueError('Pattern "{0}" exists with a different or ambiguous definition.'.format(api.name(element)))
        if not create:
            return None  # Preview: this pattern will be imported.
        new_ids = DB.ElementTransformUtils.CopyElements(source, api.ids([fid]), destination,
                                                       DB.Transform.Identity, DB.CopyPasteOptions())
        matches = [destination.GetElement(x) for x in new_ids]
        matches = [x for x in matches if isinstance(x, (DB.FillPatternElement, DB.LinePatternElement))
                   and fingerprint(x) == expected]
        if len(matches) != 1:
            raise ValueError('Could not import pattern: ' + api.name(element))
        return matches[0].Id
    return resolve


def existing_filter(destination, proposed):
    return next((x for x in api.filters(destination) if api.name(x).lower() == proposed.lower()), None)


def validate_definition(destination, source_filter):
    if not isinstance(source_filter, DB.ParameterFilterElement):
        raise ValueError('Selection filters contain project-specific element IDs and cannot be transferred.')
    categories = list(source_filter.GetCategories())
    for cid in categories:
        if DB.Category.GetCategory(destination, cid) is None:
            raise ValueError('A filter category is unavailable in the destination.')
    data = rules.encode_filter(source_filter.Document, source_filter.GetElementFilter())
    mapped = rules.decode_filter(destination, data, transfer=True)
    if mapped is not None and not DB.ParameterFilterElement.AllRuleParametersApplicable(destination, api.ids(categories), mapped):
        raise ValueError('Mapped parameters are not bound to all required destination categories.')
    return categories, mapped


def same_definition(destination, existing, categories, mapped):
    if not isinstance(existing, DB.ParameterFilterElement):
        return False
    return (set(api.eid(x) for x in existing.GetCategories()) == set(api.eid(x) for x in categories)
            and rules.encode_filter(destination, existing.GetElementFilter()) == rules.encode_filter(destination, mapped))


def import_filter(destination, source_filter, policy, cache=None):
    key = api.eid(source_filter.Id)
    if cache is not None and key in cache:
        cached = destination.GetElement(cache[key])
        if cached is not None:
            return cached
    categories, mapped = validate_definition(destination, source_filter)
    proposed = api.name(source_filter)
    existing = existing_filter(destination, proposed)
    if existing is not None and policy != 'rename':
        if same_definition(destination, existing, categories, mapped):
            if cache is not None:
                cache[key] = existing.Id
            return existing
        raise ValueError('Filter "{0}" exists with different rules/categories. Choose renamed copies.'.format(proposed))
    if policy == 'rename':
        proposed = api.unique_name(destination, proposed)
    new = DB.ParameterFilterElement.Create(destination, proposed, api.ids(categories))
    if mapped is not None:
        new.SetElementFilter(mapped)
    if cache is not None:
        cache[key] = new.Id
    return new


def preflight(source, destination, elements, policy):
    rows = []
    templates = [x for x in api.all_views(destination) if x.IsTemplate]
    for element in elements:
        row = {'view': api.name(element), 'id': api.eid(element.Id), 'status': 'ready', 'note': ''}
        try:
            api.ensure_writable(destination)
            if source.Equals(destination):
                raise ValueError('Choose a different destination project.')
            if isinstance(element, DB.ParameterFilterElement):
                categories, mapped = validate_definition(destination, element)
                existing = existing_filter(destination, api.name(element))
                if existing is not None and policy == 'skip':
                    raise ValueError('Existing name: skipped by conflict policy.')
                if existing is not None and policy == 'reuse' and not same_definition(destination, existing, categories, mapped):
                    raise ValueError('Existing filter has different rules/categories; choose renamed copies.')
                row['note'] = 'Reuse identical definition.' if existing is not None and policy == 'reuse' else 'Create filter definition.'
            elif isinstance(element, DB.View) and element.IsTemplate:
                if any(api.name(x).lower() == api.name(element).lower() for x in templates) and policy != 'rename':
                    raise ValueError('Existing template name: skipped by conflict policy.')
                missing_patterns = set()
                mapper = pattern_mapper(source, destination, False)
                for fid in element.GetOrderedFilters():
                    f = source.GetElement(fid)
                    cats, mapped = validate_definition(destination, f)
                    existing = existing_filter(destination, api.name(f))
                    if existing is not None and policy != 'rename' and not same_definition(destination, existing, cats, mapped):
                        raise ValueError('Dependent filter "{0}" conflicts; choose renamed copies.'.format(api.name(f)))
                    ogs = element.GetFilterOverrides(fid)
                    for values in api.GROUPS.values():
                        for prop, _ in values:
                            if prop.endswith('Id'):
                                value = getattr(ogs, prop)
                                if mapper(value) is None:
                                    missing_patterns.add(api.name(source.GetElement(value)))
                row['note'] = 'Copy complete template; map filter definitions and graphics.'
                if missing_patterns:
                    row['note'] += ' Import patterns: ' + ', '.join(sorted(missing_patterns))
            else:
                raise ValueError('Only parameter filters and view templates can be transferred.')
        except Exception as exc:
            row.update(status='skipped', note=str(exc))
        rows.append(row)
    return rows


class UseDestinationTypes(DB.IDuplicateTypeNamesHandler):
    def OnDuplicateTypeNamesFound(self, args):
        return DB.DuplicateTypeAction.UseDestinationTypes


def copy_template(source, destination, template, policy, cache=None):
    before_filters = set(api.eid(f.Id) for f in api.filters(destination))
    # Import source filter definitions before native template copy so parameter
    # GUID/type/binding validation remains explicit.
    mapping = {}
    for fid in template.GetOrderedFilters():
        mapping[api.eid(fid)] = import_filter(destination, source.GetElement(fid), policy, cache).Id
    options = DB.CopyPasteOptions()
    options.SetDuplicateTypeNamesHandler(UseDestinationTypes())
    copied = DB.ElementTransformUtils.CopyElements(source, api.ids([template.Id]), destination,
                                                  DB.Transform.Identity, options)
    targets = [destination.GetElement(x) for x in copied]
    targets = [x for x in targets if isinstance(x, DB.View) and x.IsTemplate]
    if len(targets) != 1:
        raise ValueError('Native copy did not produce exactly one view template.')
    target = targets[0]
    existing_names = set(api.name(x).lower() for x in api.all_views(destination) if x.Id != target.Id)
    proposed = api.name(template)
    base, index = proposed, 2
    while proposed.lower() in existing_names:
        proposed = '{0} ({1})'.format(base, index)
        index += 1
    target.Name = proposed
    for fid in list(target.GetOrderedFilters()):
        target.RemoveFilter(fid)
    mapper = pattern_mapper(source, destination, True)
    for fid in template.GetOrderedFilters():
        mapped_id = mapping[api.eid(fid)]
        target.AddFilter(mapped_id)
        overrides = api.merge_overrides(template.GetFilterOverrides(fid), DB.OverrideGraphicSettings(),
                                        list(api.GROUPS.keys()), mapper)
        target.SetFilterOverrides(mapped_id, overrides)
        target.SetFilterVisibility(mapped_id, template.GetFilterVisibility(fid))
        target.SetIsFilterEnabled(mapped_id, template.GetIsFilterEnabled(fid))
    # Remove only redundant, unused filter definitions introduced by native
    # template copying. Other copied dependencies remain part of the template.
    used = api.usage(destination)
    redundant = [f.Id for f in api.filters(destination)
                 if api.eid(f.Id) not in before_filters and f.Id not in list(mapping.values())
                 and not used.get(api.eid(f.Id))]
    if redundant:
        deleted = set(api.eid(x) for x in destination.Delete(api.ids(redundant)))
        if deleted - set(api.eid(x) for x in redundant):
            raise ValueError('Cleanup would delete dependent elements. Template transfer rolled back.')
    return target


def execute(source, destination, plan, policy):
    group = DB.TransactionGroup(destination, 'TPT View Filter Manager - transfer')
    group.Start()
    result = []
    cache = {}
    try:
        for item in plan:
            row = dict(item)
            if row['status'] != 'ready':
                result.append(row)
                continue
            element = source.GetElement(DB.ElementId(row['id']))
            previous_cache = dict(cache)
            try:
                def apply():
                    if isinstance(element, DB.ParameterFilterElement):
                        return import_filter(destination, element, policy, cache)
                    return copy_template(source, destination, element, policy, cache)
                new = api.transaction(destination, 'Transfer: ' + api.name(element), apply)
                row.update(status='completed', note='Destination: ' + api.name(new))
            except Exception as exc:
                cache.clear()
                cache.update(previous_cache)
                row.update(status='failed', note=str(exc))
            result.append(row)
        group.Assimilate()
    except Exception:
        if group.GetStatus() == DB.TransactionStatus.Started:
            group.RollBack()
        raise
    return result
