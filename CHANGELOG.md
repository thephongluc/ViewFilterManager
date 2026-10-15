# Changelog

## 2.0.2 — 2026-10-15

- Move the standalone command to its own View Filter Manager ribbon tab, separate from TPT and pyRevit.
- Install the complete runtime beside the startup DLL in Revit's standard add-ins directory.
- Remove the runtime-location pointer from new installations, avoiding the split-folder lookup that failed in a desktop Revit session after the 2.0.1 bootstrap repair.
- Validate the actual production runtime resolver against an installed-layout fixture.
- Preserve the stable installer identity and upgrade/uninstall tracking.

## 2.0.1 — 2026-10-15

- Fix Revit startup reporting the installed assembly as missing.
- Register `TPTViewFilterManager.dll` in Revit's standard current-user add-ins folder, with a pointer to the versioned runtime payload.
- Keep existing runtime/upgrade/uninstall locations and stable product IDs.
- Verify bootstrap registration and runtime pointer in installer lifecycle tests.
- Confirm actual Revit 2026.4 startup and ribbon registration through its startup journal; native model operations remain separately pending.

## 2.0.0 — 2026-10-15

- First standalone Revit 2026 add-in, migrated from the TPT pyRevit View Filter Manager 1.2.1.
- Independent .NET ribbon/command host, bundled IronPython 3 runtime and replacement WPF services; no pyRevit/Python installation required.
- Preserves copy/order/explorer/rule-editor/transfer/report workflows, Ctrl/Shift selection, resizable columns and whole-word batch renaming.
- Versioned per-user EXE installer, update/repair/uninstall support, downgrade/ownership checks, release ZIPs and SHA-256 checksums.
- Dedicated repository, semantic version source and CI/release workflows.

Live Revit acceptance remains pending; see docs/REVIT-ACCEPTANCE.md.
