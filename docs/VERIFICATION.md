# Release 2.0.3 verification — 2026-10-15

- Visible installer, load-prompt registration, main window and auxiliary dialog names use View Filter Manager; the startup DLL is ViewFilterManager.Addin.dll.
- Original installer/AddIn IDs and existing internal storage location are retained for upgrade/uninstall continuity.
- Rounded monochrome funnel/magnifier source SVG, transparent 16/32/64/256 px PNGs and multi-resolution Windows ICO are supplied. WPF windows load the new icon; installer and installed-app entry use the ICO.
- Automated build, WPF and installer checks are run for this release. Revit's unsigned load prompt and the ribbon/window appearance require visual acceptance after restart.

# Release 2.0.2 verification — 2026-10-15

- The complete startup DLL, runtime, dependencies and Content now install together in the standard Revit add-ins version folder. New installations have no runtime pointer.
- Production Installation.Root is invoked in the .NET harness against a physical installed-layout fixture; the resolved runtime path must match its containing folder.
- Installer lifecycle checks verify the colocated runtime and absence of a location pointer, plus repair/upgrade/downgrade refusal/uninstall.
- Normal desktop Revit 2026.4 startup journal.0185.txt confirms version 2.0.2.0 loaded with NoError and registered its command after the runtime layout fix. No project was opened or modified. The subsequent dedicated ribbon tab change requires visual acceptance after restart. Native model operations remain separately pending.

# Previous 2.0.1 checks (superseded layout)

- Fixes a startup rejection observed in the original 2.0.0 local registration despite the DLL existing on disk.
- Installs `TPTViewFilterManager.dll` in the standard current-user Revit add-ins directory. A UTF-8 runtime pointer locates the existing LocalAppData versioned payload.
- Actual Revit 2026.4 startup confirmed for the installed 2.0.1 patch: journal.0183.txt records `Starting External Application: TPT View Filter Manager`, assembly version `2.0.1.0`, creation of `TPT.Standalone.ViewFilterManager`, and add-in load result `NoError`.
- No project was opened or modified in the startup test. Model editing/transfer acceptance remains pending.
- All 82 offline regression tests and the embedded WPF/private dependency-context tests pass.
- Installer lifecycle checks pass with the bootstrap location and runtime-pointer validation, including repair, upgrade, downgrade refusal and uninstall.

# Original standalone verification

- Both .NET 8 x64 projects compile with zero warnings/errors against installed Revit 2026.4 references.
- The add-in entry point also compiles with zero warnings/errors using pinned reference-only NuGet API packages, matching the GitHub-hosted build path.
- All 82 carried-forward offline regression tests pass. Their Revit document/model operations are mocked.
- The actual embedded IronPython 3.4.2/.NET 8 engine imports the migrated application and independent forms services without pyRevit.
- All five application XAML windows load with their real event handlers; real WPF two-way checkbox binding, INotifyPropertyChanged, underscore labels, Unicode word matching, JSON and UUID generation pass.
- The same private assembly-load context used by the Revit command also passes the full window/binding harness alongside an already loaded default-context runtime.
- Independent text-input and category/view selection dialogs initialize and retain checked state.
- Inno Setup 6.4.3 compiles the Windows x64 EXE.
- Isolated installer lifecycle tests pass: foreign manifest refusal, all installed payload files verified by SHA-256, install, same-version repair, upgrade fixture, downgrade refusal and uninstall of both version folders/manifest. The upgrade fixture uses the known 2.0.0 payload with a test-only 2.0.1 installer label; it is not published.
- An installer version-record encoding issue found during testing was fixed and the full lifecycle rerun successfully.
- Autodesk DLLs are absent from the distributable payload.

**Live Revit model testing is pending.** The offline engine harness deliberately stubs Revit model interfaces; it verifies the standalone host/WPF integration, not native API model behavior. Complete REVIT-ACCEPTANCE.md on disposable projects before production use. Revit 2026.5/.NET 10 transitions and other Revit releases have not been validated.

Release installers are not Authenticode-signed. SHA-256 checksums are shipped with EXE/ZIP assets; validate downloads from the repository's Releases page.
