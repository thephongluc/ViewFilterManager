# Detailed workflows

Migrated from pyRevit v1.2.1; launch from the standalone TPT View Filter Manager panel.

## Whole-word matching in 1.2.1

Batch Rename defaults to **Whole words only**. Spaces, punctuation, hyphens and
underscores delimit words; Unicode letters and digits stay within a word.
`Geschossdecke → Geschossdecken` changes `Geschossdecke - Substrat` and
`Geschossdecke_Innen`, but leaves `Geschossdecken - Innen` unchanged. Disable
Whole words only to replace fragments/codes inside words. Match case remains
independent. Reset Names restores both matching options to their checked defaults.
Click Update Preview after changing options; no model names change until Apply.

## Batch Rename in 1.2.0

Open **Edit → Batch Rename…**. The separate dialog shows every project filter,
with the middle explorer's checked filters preselected. Parameter and selection
filters are supported. The existing Rename command still renames one filter.

- Check rows using checkboxes/current-name labels, Ctrl-click or Shift-click.
- Set literal Find/Replace (Match case is initially on), Prefix and/or Suffix.
- Update Preview builds checked rows from original names, replacing manual edits
  on those rows. Empty Find skips replacement; repeated previews never stack affixes.
- Edit New name directly. Unchecked rows are not renamed.
- Reset Names restores every row and clears fields without changing checks.
- Resize columns by dragging header boundaries. Counts show checked, changed
  and invalid rows; invalid row statuses appear red.
- Apply Rename is disabled until a checked row changes and all checked rows pass
  validation. Duplicate and invalid names block the whole batch, including clashes
  with unchecked filters. Cancel makes no model changes.

Apply rechecks filter IDs, original names and the full current name inventory.
Revit NamingUtils validates characters and compares duplicate names; the native
name setter remains the final authority on additional restrictions. Temporary
unique names allow swaps in one transaction. Any failure restores the entire
batch; success gives one Revit Undo step. Definitions, assignments and graphics
remain attached to the same filter IDs. After success the manager refreshes and
restores its existing selections by ID, subject to its active display filters.

## Name display fix in 1.1.1

Checkbox labels display underscores literally, including repeated and trailing
underscores. WPF access-key parsing previously hid single underscores in these
labels; underlying Revit names and IDs were unaffected. Both the main manager
and Transfer window now use explicit TextBlock content templates. Offline WPF
checks verify representative underscore names through both list/tree templates.

## Selection and column widths in 1.1.2

Click a checkbox or its label to toggle that item without clearing other checks.
Ctrl-click also toggles individual items. Shift-click checks the inclusive range
from the last clicked item, retaining other checks. In trees, ranges include only
visible rows; checking a parent still checks all its children. These controls
apply to main-window lists/trees and the Transfer elements/project lists.
Drag the gray vertical dividers to resize the four main columns or the two
Transfer columns. Minimum widths keep controls usable.

## Screenshot workflows

The main window follows the reference's numbered four-column layout. The Edit,
Explore and View Filter Manager menus provide editing, reports, presets and the
separate Transfer window. Check All/None and Expand/Collapse operate on their
respective lists/trees. Checking a tree parent checks its children; partially
selected branches show an indeterminate checkbox.

1. Check view types to narrow source views/templates, destination trees and usage.
2. Select a source and check its filters. Choose alphabetical, source V/G, or an
   imported/custom sequence. Import and Save list use UTF-8 text files containing
   one filter name per line. Move Up/Down adjusts the custom sequence.
3. Check each override property separately: overall filter visibility, projection/cut line
   weight, colour and pattern; foreground/background pattern visibility, colour
   and pattern; transparency, halftone, detail level and filter enabled state.
   All properties are initially checked. Unchecked values preserve destination
   settings. Newly added filters start with Revit defaults for unchecked values.
4. Check destination views/templates in the hierarchical tree. Switch to
   **Filters of source view/template** to select destinations per filter; only
   the selected filter/view pairs are copied. Eligible views without a filter
   are included so Filters copying can add it. The filter-mode tree has a yellow
   border, matching the reference.
5. Enable Reorder and choose placement. With Reorder off, missing filters append.
6. Select Filters and/or Overrides, preview, then Copy. Overrides is initially
   selected. Overrides-only updates existing filters and reports missing ones;
   it never adds or reorders filters. Filters-only preserves existing graphics.

Source views controlled by templates read their effective settings from those
controlling templates. Template-controlled destinations are marked and skipped;
select their template instead. Editing a template affects its controlled views.

The explorer groups filter categories and usage under expandable checked nodes.
Used filter names are highlighted green. **Show project parameters** displays
bound parameters, binding type and categories. The missing-category report
compares selected filter category sets with their union, reproducing the blue
text report in the reference. In parameter mode it reports bound categories
missing from the selected source filters. Reports open in a separate window and
can be saved as text.

### Placement rules

| Mode | Result |
| --- | --- |
| Append missing filters | Leave all existing filters in place; append only missing selected filters. |
| Stack selected filters at end | Move the selected filters into one block at the end. |
| Insert selected block at position | Remove the selected filters, then insert their block at a 1-based position in the remaining list. Oversized positions append. |
| Keep common-filter anchors | Keep common filters in their destination order; insert missing selected filters relative to those anchors. |

The anchor algorithm uses the selected source sequence. New filters following a
selected common filter are inserted directly after that filter. New filters
before the first selected common filter are inserted immediately before it. If
there is no common filter, selected filters append. If common anchors occur in a
different order in the destination, their destination order wins and the report
explains this. Unrelated destination filters always retain their relative order.

Example: destination `Include accessories â†’ Other`, selection
`Include accessories â†’ Fire 60 â†’ Fire 120` becomes
`Include accessories â†’ Fire 60 â†’ Fire 120 â†’ Other`.

The selected sorting mode determines the copy sequence. Moving or sorting this
list does not edit the source view. Presets store copy settings, granular override
selections, source/filter identity, sequence and destination selection, including
per-filter/view pairs. Older version 1 presets are migrated when loaded.
Cross-project presets match the source and filters by name when required;
destinations restore only matching UniqueIds. Missing items are reported.

## Library and cleanup

Inspect all, used, unused or categories-only filters. Usage includes compatible
views and templates directly containing a filter. A controlled view may inherit
its filters from its template; the template is the edit target.

- Create and edit parameter filters with categories and nested AND/OR groups.
- Add or replace text/numeric/ElementId rules; remove rules or groups.
- Preserve existing parameter-group inversion and inverse rules.
- Rename or duplicate parameter and selection filters.
- Edit the member IDs of existing selection filters.
- Remove selected filters from chosen views/templates without deleting definitions.
- Purge selected unused definitions, with a fresh usage check and confirmation.
- Export every filter's categories, rules, usage, order, visibility, enabled state
  and graphics to CSV or JSON. CSV uses UTF-8 with a BOM for Excel.

The rule editor lists parameters common to the selected categories. Text values
are case-insensitive as in Revit. Yes/No uses integer 1/0. Measurable custom
parameters accept project units; built-in parameters also accept project units
when a parameter definition can be sampled from existing elements/types. If
the unit specification is unavailable, use `internal:<number>` explicitly;
lengths are in feet. Dimensionless numeric parameters accept ordinary numbers.
ElementId rules require the referenced element's Revit ID.

Empty AND/OR groups cannot be saved. Clearing all rules creates a categories-only
filter. Editing a used definition changes every view/template using it. Native
Revit validates category applicability and allowable rule-tree structure; invalid
edits roll back. Unknown rule classes are reported and are not silently replaced.
Categories can be changed without changing existing rules, subject to validation.

Purge will not delete a filter still used by a compatible view/template. If Revit
reports additional dependent elements during deletion, the operation rolls back.
Revit Undo restores committed cleanup operations.

## Cross-project transfer

Open the projects before launching the manager. Open the separate Transfer
window, choose a source, check parameter filters and/or complete view templates
in its element tree, and check one or more destination projects. Template
branches expose dependent filters. Preview, then Transfer. Project selection includes open, unlinked, non-family documents.

Conflict policies:

- **Skip existing names:** skip independently selected filters/templates whose
  names already exist. Template dependencies may reuse an identical filter.
- **Reuse identical filters; skip templates:** reuse filters only when their
  mapped categories and serialized rule trees match; existing template names skip.
- **Create renamed copies:** create unique names such as `Name (2)`; do not
  overwrite existing definitions or templates.

Shared parameters match by GUID and data type. Project parameters require a
unique name, data type and matching instance/type binding. Parameters must
already be bound to the required destination categories; the tool does not create
or rebind project/shared parameters. Workset rules map workset name and kind.
Positive ElementId rules require a unique named matching definition (class,
category/family for types, and data type for global parameters). References to
ordinary model instances cannot be transferred. Selection filters cannot be
transferred because their member IDs are project-specific.

Template transfer uses Revit's native document-to-document copy for the complete
template, then explicitly rebuilds its filter stack with validated parameter
mapping and remapped graphic pattern IDs. Missing filter-override fill/line
patterns are imported. A same-name pattern with a different definition is a
conflict; it is not silently replaced. Same-name native dependent element types
use destination types, as stated in the transfer panel/confirmation. Other native
template properties and dependencies follow Revit's native copy semantics.
Within each destination batch, templates sharing a source filter reuse the same
imported definition, including when creating renamed copies.

Each item transfers inside its own transaction. A failed item rolls back, and the
batch continues. Successful transfers are assimilated into one Undo operation per destination project. The source project is not modified. Documents are not saved by this tool.
