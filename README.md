# TPT View Filter Manager

Standalone Windows add-in for **Autodesk Revit 2026**, preserving the workflows of the TPT pyRevit View Filter Manager v1.2.1. Current standalone version: **2.0.1**.

## Install

Download the versioned **Revit2026-Setup.exe** from [Releases](https://github.com/thephongluc/ViewFilterManager/releases). Save and close Revit, run setup under your normal Windows account, then restart Revit and open a project. Use **TPT → View Filter Manager → View Filter Manager**.

The EXE is the installer; editing models happens inside Revit. There is no dependency on pyRevit or a separately installed Python. Windows x64 and Revit 2026 are required. This release builds against the Revit 2026 API/.NET 8 and has been checked locally against 2026.4; newer Revit runtime transitions require separate live acceptance testing.

The unsigned first release can trigger Windows/Revit publisher prompts. Verify the release SHA-256 checksum before installation. No automatic updater downloads or executes code; install newer versioned releases yourself.

Setup registers the current user in `%APPDATA%\Autodesk\Revit\Addins\2026\ViewFilterManager.addin`, and places each version in `%LOCALAPPDATA%\TPT\ViewFilterManager\Versions\<version>`. A small startup DLL and runtime-location pointer are registered under `%APPDATA%\Autodesk\Revit\Addins\2026\ViewFilterManager\Versions\<version>`. This standard bootstrap location fixes the 2.0.0 startup rejection. Updating requires Revit to be closed, preserves earlier version files and blocks accidental downgrade. The stable Windows app entry supports repair by rerunning setup and uninstall through Settings → Apps. Uninstall removes registered product files, while logs outside version folders can remain for diagnostics.

Your old pyRevit tool remains unchanged and may coexist. Its panel is **View Filters**; this add-in uses the separate **View Filter Manager** panel. Revit models and user-created TXT/JSON/CSV files are never installed over or removed.

## Workflows

- Copy checked filters and individual graphics/visibility/enabled properties across views/templates; preview changes first.
- Order filters alphabetically, by V/G order or an imported/custom list; append, stack, place at a position or retain common anchors.
- Explore usage, filter categories and project parameters; report missing categories.
- Create/edit nested AND/OR filter rules and categories, rename/duplicate filters, edit selection members, remove assignments and purge unused definitions.
- Batch rename with live validation, literal find/replace, whole-word matching, case matching, prefixes/suffixes and manual proposed names. Whole-word matching treats spaces, punctuation, hyphens and underscores as separators. Swaps use temporary names and commit as one Undo operation.
- Transfer validated filters and complete templates to multiple open projects, with explicit name conflicts and dependency/parameter mapping.
- Export CSV/JSON reports; save/import checked-filter TXT lists and copy presets.
- Ctrl-click toggles checks; Shift-click checks ranges. Drag column dividers to resize the main/Transfer windows and rename table.

Edit actions use checked filters in the middle explorer. Copy uses checked source filters on the left and destinations on the right. Template-controlled destinations are skipped; select their controlling template instead. Changes to a shared filter definition affect every view using it.

The dialogs remain modal so Revit API operations stay inside the external command context. Existing safety checks, transaction rollback and Undo behavior are retained. See [workflow guide](docs/WORKFLOWS.md) and [live acceptance checklist](docs/REVIT-ACCEPTANCE.md).

## Build and verify

Use Windows x64, .NET SDK 8 or newer, Python 3 for offline tests, and Inno Setup 6. With Revit 2026 installed, builds use its API references. CI uses pinned Nice3point Revit API reference-only packages when local Autodesk references are absent; Autodesk DLLs are never shipped.

```powershell
.\scripts\Build.ps1 -Iscc 'C:\Program Files (x86)\Inno Setup 6\ISCC.exe'
```

Outputs go to `artifacts/`: versioned Setup EXE, portable payload ZIP and SHA256SUMS.txt. The portable ZIP is intended for managed deployment and does not register the add-in by itself; use the installer for normal installation. `-NoInstaller` builds and tests without Inno Setup. `-RevitDir` overrides a custom Revit installation path.

The single `VERSION` file drives .NET assembly/file versions, Python UI version, installer version and release filenames. Tags use `vMAJOR.MINOR.PATCH`. CI tests pull requests and builds installers for pushed release tags, publishing EXE/ZIP/checksums as draft releases for review.

## Architecture and verification limits

A compiled .NET external application registers the ribbon and invokes a private assembly-load context. A dedicated embedded IronPython 3.4.2 runtime hosts the migrated Python filter logic. An independently implemented WPF forms layer replaces every pyRevit dependency. Scripting assemblies are isolated from other add-ins; Revit and WPF assemblies stay shared with the host.

82 offline regression checks exercise filter operations through API mocks. The standalone engine harness additionally loads real WPF windows with their event handlers, verifies two-way property binding and literal labels, and renders previews. These checks do not establish native Revit model behavior. **Actual Revit 2026.4 startup and ribbon registration are verified for 2.0.1. Live model editing/transfer acceptance is pending.** Installer lifecycle tests are recorded separately in docs/VERIFICATION.md.

Errors opening the tool are written to `%LOCALAPPDATA%\TPT\ViewFilterManager\Logs\last-error.txt`. Reports can be saved from the UI. No telemetry is sent.
