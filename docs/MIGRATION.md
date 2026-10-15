# Migration from pyRevit 1.2.1

Version 2.0.0 keeps all filter algorithms and the six workflows (copy/order, explore, edit, batch rename, transfer and reports). The earlier release's 82 regression cases are carried forward.

All `pyrevit` imports have been replaced with the independent `vfm_host` module. Its forms services implement only the dialogs used by this application: WPF window loading, reactive property notifications, message/file/input dialogs and the category/view checkbox selector.

The runtime is IronPython 3.4.2 embedded as private .NET assemblies. It is installed with the add-in, including the standard library and licenses; Python/pyRevit are not prerequisites. The .NET entry point owns ribbon registration, project availability, Revit window ownership, API command context, dependency isolation and error logging.

Existing source, presets and model content are not migrated or overwritten by the installer. Existing presets remain supported by the same loader. No automatic removal of the pyRevit button is performed.

Release numbering changes from the pyRevit 1.x series to the standalone 2.x series because installation and hosting change. The standalone add-in has its own stable manifest GUID and installer AppId, which must not be changed for updates.
