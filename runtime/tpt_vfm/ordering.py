# -*- coding: utf-8 -*-
"""Pure ordering logic; no Revit dependencies. Display sorting is separate."""


def unique(values):
    result = []
    for value in values:
        if value not in result:
            result.append(value)
    return result


def ordered_filters(existing, selected, mode='append', position=1):
    """Return (order, note). All ids occur once; unrelated order is stable.

    append: leave existing filters in place, append missing ones.
    stacked: remove selected filters and append the selected block.
    position: remove selected filters, insert block at one-based position.
    anchors: keep common filters in destination order. Each new filter goes
    after its nearest preceding selected common filter in source order;
    before-first items go before that source anchor. No common filter means
    append. Reversed destination anchors are never moved.
    """
    existing, selected = unique(existing), unique(selected)
    if mode == 'append':
        return existing + [x for x in selected if x not in existing], ''
    rest = [x for x in existing if x not in selected]
    if mode == 'stacked':
        return rest + selected, ''
    if mode == 'position':
        if int(position) < 1:
            raise ValueError('Position must be at least 1.')
        i = min(int(position) - 1, len(rest))
        return rest[:i] + selected + rest[i:], ''
    if mode != 'anchors':
        raise ValueError('Unknown placement mode: ' + mode)
    common = [x for x in selected if x in existing]
    if not common:
        return existing + selected, 'No common anchor: appended selected filters.'
    before, after = {}, dict((x, []) for x in common)
    pending = []
    anchor = None
    for item in selected:
        if item in common:
            if anchor is None and pending:
                before[item] = pending
                pending = []
            anchor = item
        elif anchor is None:
            pending.append(item)
        else:
            after[anchor].append(item)
    result = []
    for item in existing:
        result.extend(before.get(item, []))
        result.append(item)
        result.extend(after.get(item, []))
    note = ''
    if [x for x in existing if x in common] != common:
        note = 'Common anchors have a different order; destination anchor positions were preserved.'
    return result, note
