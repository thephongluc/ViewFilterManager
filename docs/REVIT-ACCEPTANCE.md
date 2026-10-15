# Revit 2026 acceptance checklist

Status: **pending live Revit testing**. Use a small test project and a second open
project with matching shared/project parameter bindings. Record the exact Revit
build, add-in version and embedded IronPython engine, and attach any saved report for failures.

## Launch and selection

- [ ] Install Setup EXE with Revit closed; TPT → View Filter Manager → View Filter Manager appears with its icon.
- [ ] Opening a project launches the dialog without errors; family documents disable it.
- [ ] View/template/type/name filters work; All/None check the visible items.
- [ ] Non-English names and duplicate view titles display correctly.
- [ ] Alphabetical sorting copies in alphabetical order; V/G sorting restores native source order.
- [ ] Move up/down changes the planned sequence without changing the source.
- [ ] Source view controlled by a template reads the template's filter settings.

- [ ] Parent checkbox changes propagate to children and partial branches are indeterminate.
- [ ] Imported TXT sequences and saved checked-filter lists round-trip non-English names.
- [ ] Filter-mode destination selection copies only selected filter/view pairs.
- [ ] Used filters highlight green; project parameters display bindings and categories.
- [ ] Doors/Walls checked-category coverage produces the reference-style report.
- [ ] Save/load presets restores granular properties and per-filter/view destinations.

- [ ] Ctrl-click toggles individual list/tree checks without clearing others.
- [ ] Shift-click checks forward/reverse ranges from the anchor, retaining other checks.
- [ ] Tree range follows visible rows and parent checks still cascade to descendants.
- [ ] Selection after source/search refresh does not use a stale range anchor.
- [ ] Drag all three main-window dividers and the Transfer divider; adjacent widths change.

## Copy modes and graphics

- [ ] Filters-only adds missing filters without changing existing destination overrides.
- [ ] Overrides-only never adds or reorders missing filters and reports them.
- [ ] Projection-only copying preserves cut graphics, surface graphics and states.
- [ ] Foreground/background pattern IDs, colours and visibility copy correctly.
- [ ] Transparency, halftone and detail level each copy independently.
- [ ] Visibility and enabled state each copy independently when selected.
- [ ] Newly added filters keep Revit defaults for unchecked properties.
- [ ] Template-controlled destinations skip with the controlling template's name.
- [ ] Template with filter control unchecked permits editing the view's local filters.

## Ordering and rollback

- [ ] Append does not move existing filters.
- [ ] Stacked creates a selected block after unrelated filters.
- [ ] Position is 1-based and clamps to the end when oversized.
- [ ] Common anchor inserts fire-rating filters beneath the selected existing anchor.
- [ ] Items preceding the first anchor insert before it.
- [ ] Missing anchors append and produce an explanatory note.
- [ ] Reversed multiple anchors retain destination anchor order and report it.
- [ ] Unrelated filter overrides, visibility and enabled state survive reordering.
- [ ] Repeating the same operation does not duplicate filters or move them again.
- [ ] A worksharing-locked destination fails without changing that destination.
- [ ] Other valid destinations complete after an individual failure.
- [ ] One Undo operation restores all successful batch changes.

## Library, rules and cleanup

- [ ] Create a categories-only parameter filter.
- [ ] Create and edit nested AND/OR groups with text and numeric rules.
- [ ] Check built-in and shared/project parameter values in project units.
- [ ] Check integer/Yes-No, ElementId, Has value and Has no value rules.
- [ ] Edit an existing inverse rule/filter without losing its inversion or nesting.
- [ ] Invalid or empty groups roll back without altering the existing definition.
- [ ] Category change with inapplicable rules rolls back.
- [ ] Rename and duplicate preserve definition and existing assignments.
- [ ] Selection-filter duplicate/member edit preserves valid members.
- [ ] Usage lists include views/templates using a selected filter.
- [ ] Remove from selected views preserves the project definition.
- [ ] Used filters cannot be purged; unused filters can be purged and restored by Undo.
- [ ] CSV opens in Excel with non-English names intact; JSON includes rule and graphics data.
- [ ] Presets preserve settings and selected sequence and report unavailable filters.

## Transfer

- [ ] Separate Transfer window selects multiple open destination projects.
- [ ] Template/filter tree parent selection and dependent filters behave correctly.
- [ ] Shared dependencies create only one renamed filter per destination batch.
- [ ] Transfer results and Undo are independent for each destination project.

- [ ] Same shared GUID maps even when the parameter display name differs.
- [ ] Same parameter name with a different shared GUID is rejected.
- [ ] Missing, ambiguously named or wrongly typed/bound project parameters are rejected.
- [ ] Selection filters and ordinary-instance ElementId rules skip with an explanation.
- [ ] Workset rules map by name/kind, not source workset integer IDs.
- [ ] Named referenced types/materials/levels map uniquely; missing references skip.
- [ ] Skip and reuse policies behave as documented on existing names.
- [ ] Rename creates unique definitions/templates without overwriting existing ones.
- [ ] Complete template native copy succeeds in the installed Revit build.
- [ ] Transferred filter stack, graphics, visibility and enabled state match the source.
- [ ] Missing patterns import; same-name patterns with different definitions skip.
- [ ] Native template properties outside filters behave according to Revit native copy.
- [ ] A failed transfer rolls back all definitions/dependencies introduced by that item.
- [ ] Successful items form one Undo operation in the destination.
- [ ] Source project is unchanged and neither project is automatically saved.

## Batch Rename

- [ ] Open Batch Rename with explorer checks; all project parameter/selection filters appear with those checks retained.
- [ ] Ctrl-click toggles; Shift-click checks a forward/reverse range; Check All/None work.
- [ ] Resize table columns; edit a New name with underscores and Unicode intact.
- [ ] Preview applies literal find/replace, case matching, prefix and suffix from original names.
- [ ] Repeated preview does not stack affixes; manual edits are preserved until preview/reset.
- [ ] Reset restores names and clears fields while retaining checks; Cancel changes nothing.
- [ ] Duplicate, outside-batch conflict, blank and prohibited-character names block Apply.
- [ ] Unchanged/unchecked filters do not change; deleted or externally renamed filters block Apply.
- [ ] Swap two filter names successfully and verify assignments/rules/graphics remain intact.
- [ ] A native name-setter/worksharing failure rolls back all temporary and final names.
- [ ] Successful batch is one Undo step; Undo restores all names; manager selections survive refresh.

- [ ] Whole words only starts checked; singular Geschossdecke changes and existing Geschossdecken remains unchanged.
- [ ] Spaces/hyphens/underscores/punctuation delimit words; adjacent Unicode letters/digits prevent whole-word matches.
- [ ] Disabling Whole words only permits fragment replacement; Match case works in both modes.
- [ ] Reset Names restores Whole words only and Match case; Update Preview reflects changed options.

## Standalone host and installer

- [ ] Launch with pyRevit absent/disabled; all windows and category/view picker dialogs work.
- [ ] Launch beside pyRevit and other scripting add-ins; no assembly/binding conflicts.
- [ ] Revit 2026 project availability is enforced; family documents/no document disable the command.
- [ ] Input dialogs, file dialogs and confirmations have usable focus/ownership.
- [ ] Install/repair/update/uninstall with Revit closed; manifest and installed versions point to the expected DLL.
- [ ] Setup refuses a newer installed version, foreign registration, custom destination or running Revit.
- [ ] First production-model validation uses a disposable copy; record Revit patch level.

## 2.0.1 startup repair evidence

- [x] Real Revit 2026.4 startup loads the standard-directory bootstrap and reports version 2.0.1.0 with NoError.
- [ ] The standalone ribbon button appears on its dedicated View Filter Manager tab (updated in 2.0.2; visual acceptance pending).
- [ ] Validate opening the manager and native model workflows in a disposable project.
