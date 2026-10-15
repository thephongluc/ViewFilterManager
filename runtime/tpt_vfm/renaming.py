# -*- coding: utf-8 -*-
"""Pure batch rename preview rules; names and IDs are kept separate."""
import re


def transform(original, find='', replacement='', prefix='', suffix='', match_case=True, whole_words=True):
    name = original
    if find:
        if whole_words:
            # Unicode letters/digits are word content; underscore is a separator.
            pattern = u'(?<![^\\W_])' + re.escape(find) + u'(?![^\\W_])'
            flags = re.UNICODE | (0 if match_case else re.IGNORECASE)
            name = re.sub(pattern, lambda match: replacement, name, flags=flags)
        elif match_case:
            name = name.replace(find, replacement)
        else:
            name = re.sub(re.escape(find), lambda match: replacement, name, flags=re.UNICODE | re.IGNORECASE)
    return prefix + name + suffix


def prepare(rows, inventory, valid_name, compare_names):
    """rows: id/original/proposed/checked dictionaries; inventory: id -> name."""
    selected = [r for r in rows if r['checked']]
    errors, changes = {}, []
    finals = dict(inventory)
    for row in selected:
        key, proposed = row['id'], row['proposed']
        if key not in inventory:
            errors[key] = 'Filter no longer exists. Reopen Batch Rename.'
        elif inventory[key] != row['original']:
            errors[key] = 'Name changed since opening. Reopen Batch Rename.'
        elif not proposed.strip():
            errors[key] = 'Name cannot be blank.'
        elif not valid_name(proposed):
            errors[key] = 'Name contains characters Revit does not allow.'
        finals[key] = proposed
    for row in selected:
        key = row['id']
        if key in errors:
            continue
        for other_id, other_name in finals.items():
            if other_id != key and compare_names(row['proposed'], other_name) == 0:
                errors[key] = 'Duplicate name: ' + other_name
                break
        if key not in errors and row['proposed'] != row['original']:
            changes.append(row)
    return errors, changes
