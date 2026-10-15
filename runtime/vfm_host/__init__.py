"""Standalone Revit host services; no pyRevit imports or installation."""
import clr
clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')
from Autodesk.Revit import DB
from ViewFilterManager.Runtime import Context
from . import forms

class RevitContext(object):
    @property
    def doc(self):
        app = Context.Application
        return app.ActiveUIDocument.Document if app and app.ActiveUIDocument else None

revit = RevitContext()
