"""Run in the same embedded IronPython 3 engine as the actual add-in."""
import os
import json
import io
import uuid
import clr
from System import Action
from System.Windows.Threading import DispatcherPriority
from System.Windows import Size, Rect
from System.Windows.Controls import Border
from System.Windows.Media import PixelFormats
from System.Windows.Media.Imaging import RenderTargetBitmap, PngBitmapEncoder, BitmapFrame
from System.IO import File
# API model calls are deliberately mocked here; all WPF/engine code is real.
import sys, types
host = types.ModuleType('vfm_host')
host.__path__ = [os.path.join(bundle, 'vfm_host')]
host.DB = types.SimpleNamespace(IFailuresPreprocessor=object, IDuplicateTypeNamesHandler=object)
host.revit = types.SimpleNamespace(doc=None)
sys.modules['vfm_host'] = host
from vfm_host import forms
from tpt_vfm import ui, renaming, selection

assert renaming.transform('Geschossdecken - Innen', 'Geschossdecke', 'Geschossdecken') == 'Geschossdecken - Innen'
assert renaming.transform('Geschossdecke_Innen', 'Geschossdecke', 'Geschossdecken') == 'Geschossdecken_Innen'
assert renaming.transform('Türen_ÄTüren', 'Türen', 'Doors') == 'Doors_ÄTüren'
assert json.loads(json.dumps({'name':'Türen'}))['name'] == 'Türen'
assert len(uuid.uuid4().hex) == 32
# Real ReactiveObject + Python mixin and real two-way WPF binding.
node = ui.CheckNode('GWK_SuD')
child = node.add(ui.CheckNode('Türen__'))
node.IsChecked = True
assert child.IsChecked
node.IsExpanded = True
row = forms.ChoiceRow('value', 'GWK_SuD')
# Load all XAML with its actual event handlers, not a stripped schema-only copy.
def blank(cls, filename):
    window = cls.__new__(cls)
    window._loading = True
    forms.WPFWindow.__init__(window, os.path.join(bundle, filename))
    return window
windows = []
for cls, filename in ((ui.ManagerWindow,'manager.xaml'),(ui.EditorWindow,'editor.xaml'),
                      (ui.TransferWindow,'transfer.xaml'),(ui.ReportWindow,'report.xaml'),(ui.RenameWindow,'rename.xaml')):
    window = blank(cls, filename)
    if filename == 'manager.xaml':
        window.library_filters.ItemsSource = [node]
        window.source_filters.ItemsSource = [ui.Row(None, 'Geschossdecken - Innen'), ui.Row(None,'GWK_SuD')]
        window.override_options.ItemsSource = [ui.Row(k,v) for k,v in ui.OVERRIDES]
        window.dest_views.ItemsSource = [ui.CheckNode('Views / View Templates')]
    if filename == 'transfer.xaml': window.elements.ItemsSource = [node]
    if filename == 'rename.xaml':
        assert window.rename_whole_words.IsChecked
        assert window.rename_match_case.IsChecked
        window.rename_rows.ItemsSource = [row]
    window.Measure(Size(window.Width,window.Height))
    window.Arrange(Rect(0,0,window.Width,window.Height))
    window.Dispatcher.Invoke(Action(lambda: None), DispatcherPriority.ContextIdle)
    window.UpdateLayout()
    if filename == 'manager.xaml':
        checkbox = window.Resources['CheckTree'].LoadContent()
        checkbox.DataContext = node
        checkbox.Dispatcher.Invoke(Action(lambda: None), DispatcherPriority.ContextIdle)
        checkbox.GetBindingExpression(checkbox.IsCheckedProperty).UpdateTarget()
        assert checkbox.IsChecked
        node.IsChecked = False
        checkbox.Dispatcher.Invoke(Action(lambda: None), DispatcherPriority.ContextIdle)
        assert not checkbox.IsChecked, 'INotifyPropertyChanged binding did not refresh'
        checkbox.IsChecked = True
        assert node.IsChecked, 'Two-way checkbox binding did not write Python property'
        literal = checkbox.ContentTemplate.LoadContent()
        literal.DataContext = node.Label
        literal.Dispatcher.Invoke(Action(lambda: None), DispatcherPriority.ContextIdle)
        assert literal.Text == 'GWK_SuD'
    # Render actual content while retaining the window resources.
    canvas = Border(); canvas.Resources = window.Resources; canvas.Background = window.Background
    content = window.Content; window.Content = None; canvas.Child = content
    canvas.Measure(Size(window.Width-30,window.Height-60))
    canvas.Arrange(Rect(0,0,window.Width-30,window.Height-60)); canvas.UpdateLayout()
    bitmap = RenderTargetBitmap(int(window.Width-30),int(window.Height-60),96,96,PixelFormats.Pbgra32)
    bitmap.Render(canvas)
    encoder = PngBitmapEncoder(); encoder.Frames.Add(BitmapFrame.Create(bitmap))
    stream = File.Create(os.path.join(output,filename+'.png')); encoder.Save(stream); stream.Dispose()
    window.Close()
    print('Loaded real handlers and rendered: '+filename)
input_window = forms.InputWindow('GWK_SuD','Filter name','Input smoke')
assert input_window.input.Text == 'GWK_SuD'; input_window.Close()
option = forms.TemplateListItem('Doors',True)
selection_window = forms.SelectFromList([option],None,True,'Selection smoke','Select')
assert selection_window.rows[0].IsChecked
assert selection_window.rows[0].Value == 'Doors'
selection_window.Close()
print('Independent input and category/view selector dialogs passed.')
