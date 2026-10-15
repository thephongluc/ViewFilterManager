"""Small independent WPF services used by the migrated filter manager."""
import clr
clr.AddReference('PresentationFramework')
clr.AddReference('PresentationCore')
clr.AddReference('WindowsBase')
import wpf
from System import Object
from System.Collections.ObjectModel import ObservableCollection
from System.Windows import Application, Window, MessageBox, MessageBoxButton, MessageBoxResult
from System.Windows.Input import Key
from Microsoft.Win32 import OpenFileDialog, SaveFileDialog
from ViewFilterManager.Runtime import Context, ReactiveObject

Reactive = ReactiveObject

class WPFWindow(Window):
    def __init__(self, path):
        wpf.LoadComponent(self, path)
        Context.SetOwner(self)
        self.PreviewKeyDown += self._escape
    def _escape(self, sender, args):
        if args.Key == Key.Escape:
            self.Close()
            args.Handled = True

def _owner():
    application = Application.Current
    if application:
        return next((window for window in application.Windows if window.IsActive), None)
    return None

def alert(message, title='View Filter Manager', yes=False, no=False, **kwargs):
    buttons = MessageBoxButton.YesNo if yes or no else MessageBoxButton.OK
    owner = _owner()
    result = MessageBox.Show(owner, str(message), title, buttons) if owner else MessageBox.Show(str(message), title, buttons)
    return result == MessageBoxResult.Yes if yes or no else True

def pick_file(file_ext='', **kwargs):
    dialog = OpenFileDialog()
    dialog.Filter = '{0} files|*.{0}|All files|*.*'.format(file_ext) if file_ext else 'All files|*.*'
    return dialog.FileName if (dialog.ShowDialog(_owner()) if _owner() else dialog.ShowDialog()) else None

def save_file(file_ext='', default_name='', **kwargs):
    dialog = SaveFileDialog()
    dialog.Filter = '{0} files|*.{0}|All files|*.*'.format(file_ext) if file_ext else 'All files|*.*'
    dialog.FileName, dialog.DefaultExt = default_name, '.' + file_ext
    dialog.AddExtension, dialog.OverwritePrompt = True, True
    return dialog.FileName if (dialog.ShowDialog(_owner()) if _owner() else dialog.ShowDialog()) else None

def ask_for_string(default='', prompt='', title='View Filter Manager'):
    window = InputWindow(default, prompt, title)
    return window.value if window.ShowDialog() else None

class InputWindow(WPFWindow):
    def __init__(self, value, prompt, title):
        import os
        WPFWindow.__init__(self, os.path.join(os.path.dirname(__file__), 'input.xaml'))
        self.Title, self.prompt.Text, self.input.Text, self.value = title, prompt, value, None
        self.Loaded += self.focus_input
    def focus_input(self, sender, args): self.input.Focus(); self.input.SelectAll()
    def ok_click(self, sender, args): self.value = self.input.Text; self.DialogResult = True
    def cancel_click(self, sender, args): self.DialogResult = False

class TemplateListItem(object):
    def __init__(self, item, checked=False, **kwargs): self.item, self.state = item, checked
    @property
    def name(self): return str(self.item)

class ChoiceRow(Reactive):
    def __init__(self, value, label, checked=False):
        self.Value, self.Label, self._checked = value, label, checked
    @property
    def IsChecked(self): return self._checked
    @IsChecked.setter
    def IsChecked(self, value): self._checked = bool(value); self.OnPropertyChanged('IsChecked')

class SelectFromList(WPFWindow):
    @staticmethod
    def show(choices, name_attr=None, multiselect=False, title='Select items', button_name='Select', **kwargs):
        window = SelectFromList(choices, name_attr, multiselect, title, button_name)
        if not window.ShowDialog(): return None
        values = [row.Value for row in window.rows if row.IsChecked]
        return values if multiselect else (values[0] if values else None)
    def __init__(self, choices, name_attr, multiselect, title, button_name):
        import os
        self.rows = []
        for choice in choices:
            wrapped = isinstance(choice, TemplateListItem)
            value = choice.item if wrapped else choice
            label = str(getattr(choice, name_attr)) if name_attr else choice.name if wrapped else str(choice)
            self.rows.append(ChoiceRow(value, label, choice.state if wrapped else False))
        self.multiselect, self.anchor = multiselect, None
        WPFWindow.__init__(self, os.path.join(os.path.dirname(__file__), 'select.xaml'))
        self.Title, self.accept.Content = title, button_name
        self.items.ItemsSource = self.rows
    def search_changed(self, sender, args):
        if hasattr(self, 'items'):
            text = self.search.Text.lower()
            self.items.ItemsSource = [r for r in self.rows if text in r.Label.lower()]
    def row_click(self, sender, args):
        from System.Windows.Input import Keyboard, ModifierKeys
        from tpt_vfm.selection import click_targets
        row = sender.DataContext
        if self.multiselect:
            shift = bool(Keyboard.Modifiers & ModifierKeys.Shift)
            targets = click_targets(list(self.items.Items), row, self.anchor, shift)
            value = True if shift else not row.IsChecked
            for target in targets: target.IsChecked = value
            if not shift or self.anchor is None: self.anchor = row
        else:
            for target in self.rows: target.IsChecked = target is row
        args.Handled = True
    def all_click(self, sender, args):
        if self.multiselect:
            for row in self.items.Items: row.IsChecked = True
    def none_click(self, sender, args):
        for row in self.items.Items: row.IsChecked = False
    def ok_click(self, sender, args): self.DialogResult = True
    def cancel_click(self, sender, args): self.DialogResult = False
