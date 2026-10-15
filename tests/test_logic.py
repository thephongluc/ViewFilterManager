"""Offline regression checks. API mocks are not a substitute for Revit tests."""
import ast
import copy
import importlib
import pathlib
import random
import sys
import types
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parents[1]
BUNDLE = ROOT / 'runtime'
sys.path.insert(0, str(BUNDLE))
from tpt_vfm.ordering import ordered_filters
from tpt_vfm.selection import TreeItem, checked, category_coverage


class ElementId:
    def __init__(self, value): self.Value = int(value)
    def __eq__(self, other): return isinstance(other, ElementId) and self.Value == other.Value
    def __hash__(self): return hash(self.Value)


class GenericList:
    def __class_getitem__(cls, key): return list


class Overrides:
    def __init__(self, other=None): self.values = copy.deepcopy(other.values) if other else {}
    def __getattr__(self, key):
        if key.startswith('__'): raise AttributeError(key)
        if key.startswith('Set'):
            prop = key[3:]
            if prop == 'SurfaceTransparency': prop = 'Transparency'
            if prop.endswith('PatternVisible'): prop = 'Is' + prop
            return lambda value: self.values.__setitem__(prop, value)
        return self.values.get(key, 0)


class Tx:
    def __init__(self, doc, title): self.doc, self.state = doc, 'new'
    def Start(self):
        self.state = 'started'
        self.backup = copy.deepcopy(self.doc.views)
    def GetFailureHandlingOptions(self): return self
    def SetFailuresPreprocessor(self, x): return self
    def SetClearAfterRollback(self, x): return self
    def SetFailureHandlingOptions(self, x): pass
    def Commit(self): self.state = 'committed'; return self.state
    def RollBack(self):
        self.doc.views = self.backup
        self.state = 'rolledback'
    def GetStatus(self): return self.state
    def Assimilate(self): self.state = 'committed'


class FakeView:
    def __init__(self, vid, order):
        self.Id = ElementId(vid)
        self.Name = 'View ' + str(vid)
        self.IsTemplate = True
        self.ViewTemplateId = ElementId(-1)
        self.order = list(order)
        self.states = {x: (Overrides(), False, False) for x in order}
        self.fail = False
    def GetOrderedFilters(self): return [ElementId(x) for x in self.order]
    def GetFilterOverrides(self, fid): return self.states[fid.Value][0]
    def GetFilterVisibility(self, fid): return self.states[fid.Value][1]
    def GetIsFilterEnabled(self, fid): return self.states[fid.Value][2]
    def AddFilter(self, fid):
        if self.fail: raise ValueError('locked destination')
        self.order.append(fid.Value)
        self.states[fid.Value] = (Overrides(), True, True)
    def RemoveFilter(self, fid): self.order.remove(fid.Value); del self.states[fid.Value]
    def SetFilterOverrides(self, fid, ogs):
        self.states[fid.Value] = (ogs, *self.states[fid.Value][1:])
    def SetFilterVisibility(self, fid, value):
        ogs, _, enabled = self.states[fid.Value]; self.states[fid.Value] = (ogs, value, enabled)
    def SetIsFilterEnabled(self, fid, value):
        ogs, visible, _ = self.states[fid.Value]; self.states[fid.Value] = (ogs, visible, value)


class FakeDoc:
    IsReadOnly = False
    def __init__(self, views): self.views = {v.Id.Value: v for v in views}
    def GetElement(self, fid): return self.views.get(fid.Value)


def load_api():
    db = types.SimpleNamespace(ElementId=ElementId, OverrideGraphicSettings=Overrides,
                               IFailuresPreprocessor=object, Transaction=Tx, TransactionGroup=Tx,
                               TransactionStatus=types.SimpleNamespace(Started='started', Committed='committed'),
                               BuiltInParameter=types.SimpleNamespace(VIS_GRAPHICS_FILTERS=-1),
                               Element=types.SimpleNamespace(Name=types.SimpleNamespace(GetValue=lambda x: x.Name)))
    pyrevit = types.ModuleType('vfm_host'); pyrevit.DB = db
    sys.modules['vfm_host'] = pyrevit
    for key in ('System', 'System.Collections', 'System.Collections.Generic'):
        sys.modules[key] = types.ModuleType(key)
    sys.modules['System.Collections.Generic'].List = GenericList
    return importlib.import_module('tpt_vfm.api')


api = load_api()


class Definition:
    def __init__(self, name, datatype): self.Name, self.datatype = name, datatype
    def GetDataType(self): return types.SimpleNamespace(TypeId=self.datatype)


class ParameterElement:
    def __init__(self, value, name, datatype):
        self.Id, self.definition = ElementId(value), Definition(name, datatype)
    def GetDefinition(self): return self.definition


class SharedParameterElement(ParameterElement):
    def __init__(self, value, name, datatype, guid):
        super().__init__(value, name, datatype); self.GuidValue = guid


class Collector:
    def __init__(self, doc): self.values = list(doc.parameters)
    def OfClass(self, cls): self.values = [x for x in self.values if isinstance(x, cls)]; return self
    def __iter__(self): return iter(self.values)


class ParameterDoc:
    def __init__(self, parameters):
        self.parameters = parameters
        self.ParameterBindings = types.SimpleNamespace(get_Item=lambda definition: None)
    def GetElement(self, pid): return next((x for x in self.parameters if x.Id == pid), None)


class NativeNode:
    def __init__(self, *args): self.args = args


class ParameterNode(NativeNode):
    def __init__(self, values, inverted=False): self.args, self.Inverted = values, inverted


system = sys.modules['System']
system.Enum = types.SimpleNamespace(ToObject=lambda cls, value: value)
system.Int32, system.Double = int, float
db = api.DB
db.ParameterElement, db.SharedParameterElement = ParameterElement, SharedParameterElement
db.FilteredElementCollector = Collector
db.Category = types.SimpleNamespace(IsBuiltInCategory=lambda x: False)
db.ElementFilter, db.FilterRule = object, object
db.IDuplicateTypeNamesHandler = object
db.ParameterFilterElement = type('ParameterFilterElement', (), {})
db.ParameterValueProvider = NativeNode
db.ElementParameterFilter = ParameterNode
db.LogicalAndFilter = db.LogicalOrFilter = NativeNode
for cls in ('FilterStringRule', 'FilterIntegerRule', 'FilterDoubleRule', 'FilterElementIdRule',
            'FilterGlobalParameterAssociationRule', 'HasValueFilterRule', 'HasNoValueFilterRule',
            'FilterInverseRule', 'FilterStringEquals', 'FilterNumericEquals', 'FilterStringContains'):
    setattr(db, cls, NativeNode)
from tpt_vfm import rules
from tpt_vfm import transfer


class OrderingTests(unittest.TestCase):
    def test_append_preserves_existing(self):
        self.assertEqual(ordered_filters([1, 2, 3], [2, 4])[0], [1, 2, 3, 4])
    def test_stacked_moves_existing_selection(self):
        self.assertEqual(ordered_filters([1, 2, 3], [2, 4], 'stacked')[0], [1, 3, 2, 4])
    def test_insert_position(self):
        self.assertEqual(ordered_filters([1, 2, 3], [2, 4], 'position', 2)[0], [1, 2, 4, 3])
    def test_position_clamped(self):
        self.assertEqual(ordered_filters([1], [2], 'position', 99)[0], [1, 2])
    def test_invalid_position(self):
        with self.assertRaises(ValueError): ordered_filters([1], [2], 'position', 0)
    def test_video_anchor(self):
        self.assertEqual(ordered_filters(['include', 'other'], ['include', 'fire1', 'fire2'], 'anchors')[0],
                         ['include', 'fire1', 'fire2', 'other'])
    def test_before_first_anchor(self):
        self.assertEqual(ordered_filters([9, 2, 8], [1, 2, 3], 'anchors')[0], [9, 1, 2, 3, 8])
    def test_missing_anchor(self):
        order, note = ordered_filters([1], [2, 3], 'anchors')
        self.assertEqual(order, [1, 2, 3]); self.assertIn('No common', note)
    def test_reversed_anchors(self):
        order, note = ordered_filters([4, 9, 1], [1, 2, 4, 5], 'anchors')
        self.assertEqual(order, [4, 5, 9, 1, 2]); self.assertIn('different order', note)
    def test_duplicates(self):
        self.assertEqual(ordered_filters([1, 1], [2, 2, 1])[0], [1, 2])
    def test_random_invariants(self):
        random.seed(6)
        for _ in range(300):
            existing = random.sample(range(12), random.randrange(13))
            selected = random.sample(range(12), random.randrange(13))
            for mode in ('append', 'stacked', 'position', 'anchors'):
                result, _ = ordered_filters(existing, selected, mode, 3)
                self.assertEqual(len(result), len(set(result)))
                self.assertEqual(set(result), set(existing) | set(selected))
                unrelated = [x for x in existing if x not in selected]
                self.assertEqual([x for x in result if x in unrelated], unrelated)
    def test_idempotence(self):
        for mode in ('append', 'stacked', 'position', 'anchors'):
            once, _ = ordered_filters([9, 1, 8, 4], [1, 2, 4, 5], mode, 2)
            twice, _ = ordered_filters(once, [1, 2, 4, 5], mode, 2)
            self.assertEqual(once, twice)


class CopyTests(unittest.TestCase):
    def setUp(self):
        self.source = FakeView(10, [1, 2])
        self.dest = FakeView(20, [1, 3])
        self.doc = FakeDoc([self.source, self.dest])
        self.source.states[1][0].values.update(ProjectionLineWeight=7, CutLineWeight=8)
        self.dest.states[1][0].values.update(ProjectionLineWeight=2, CutLineWeight=3)
        self.dest.states[3][0].values.update(CutLineWeight=11)
    def plan(self, mode='both', placement='anchors'):
        return api.plan_copy(self.doc, self.source, [ElementId(1), ElementId(2)], [self.dest], mode, placement, 1)
    def test_selective_merge_preserves_unchecked_properties(self):
        merged = api.merge_overrides(self.source.states[1][0], self.dest.states[1][0], ['projection'])
        self.assertEqual(merged.ProjectionLineWeight, 7)
        self.assertEqual(merged.CutLineWeight, 3)
        self.assertEqual(self.dest.states[1][0].ProjectionLineWeight, 2)
    def test_reorder_restores_unrelated_states(self):
        result = api.copy_filters(self.doc, self.source, self.plan(), 'both', ['projection'])
        self.assertEqual(result[0]['status'], 'completed')
        self.assertEqual(self.dest.order, [1, 2, 3])
        self.assertEqual(self.dest.states[3][0].CutLineWeight, 11)
        self.assertEqual(self.dest.states[3][1:], (False, False))
        self.assertEqual(self.dest.states[1][0].CutLineWeight, 3)
        self.assertEqual(self.dest.states[2][1:], (True, True))
    def test_filters_only_preserves_existing_overrides(self):
        api.copy_filters(self.doc, self.source, self.plan('filters'), 'filters', ['projection'])
        self.assertEqual(self.dest.states[1][0].ProjectionLineWeight, 2)
    def test_overrides_only_does_not_add_missing(self):
        plan = self.plan('overrides')
        self.assertIn('absent', plan[0]['note'])
        api.copy_filters(self.doc, self.source, plan, 'overrides', ['projection'])
        self.assertEqual(self.dest.order, [1, 3])
        self.assertEqual(self.dest.states[1][0].ProjectionLineWeight, 7)
    def test_visibility_enabled_are_independent(self):
        self.source.states[1] = (self.source.states[1][0], True, True)
        api.copy_filters(self.doc, self.source, self.plan('overrides'), 'overrides', ['visibility'])
        self.assertEqual(self.dest.states[1][1:], (True, False))
    def test_readonly_is_skipped(self):
        self.doc.IsReadOnly = True
        self.assertEqual(self.plan()[0]['status'], 'skipped')
    def test_source_destination_skipped(self):
        plan = api.plan_copy(self.doc, self.source, [ElementId(1)], [self.source], 'both', 'append', 1)
        self.assertEqual(plan[0]['status'], 'skipped')
    def test_stale_preview_fails_without_overwriting(self):
        plan = self.plan()
        self.dest.order.reverse()
        rows = api.copy_filters(self.doc, self.source, plan, 'both', ['projection'])
        self.assertEqual(rows[0]['status'], 'failed')
        self.assertEqual(self.doc.GetElement(ElementId(20)).order, [3, 1])
    def test_failed_destination_rolls_back_and_batch_continues(self):
        self.dest.fail = True
        other = FakeView(30, [3]); self.doc.views[30] = other
        plan = api.plan_copy(self.doc, self.source, [ElementId(1), ElementId(2)],
                             [self.dest, other], 'both', 'append', 1)
        rows = api.copy_filters(self.doc, self.source, plan, 'both', ['projection'])
        self.assertEqual([r['status'] for r in rows], ['failed', 'completed'])
        self.assertEqual(self.doc.views[20].order, [1, 3])
        self.assertEqual(self.doc.views[30].order, [3, 1, 2])


class RuleTransferTests(unittest.TestCase):
    def info(self, doc, element): return rules.parameter_info(doc, element.Id)
    def test_shared_guid_wins_over_name(self):
        source = SharedParameterElement(1, 'Fire rating', 'string.text', 'GUID-1')
        wrong = SharedParameterElement(2, 'Fire rating', 'string.text', 'GUID-2')
        right = SharedParameterElement(3, 'Renamed rating', 'string.text', 'GUID-1')
        doc = ParameterDoc([source])
        self.assertEqual(rules.map_parameter(ParameterDoc([wrong, right]), self.info(doc, source)).Value, 3)
    def test_same_name_wrong_guid_rejected(self):
        source = SharedParameterElement(1, 'Rating', 'string.text', 'GUID-1')
        with self.assertRaises(ValueError):
            rules.map_parameter(ParameterDoc([SharedParameterElement(2, 'Rating', 'string.text', 'GUID-2')]), self.info(ParameterDoc([source]), source))
    def test_project_parameter_type_must_match(self):
        source = ParameterElement(1, 'Rating', 'string.text')
        with self.assertRaises(ValueError):
            rules.map_parameter(ParameterDoc([ParameterElement(2, 'Rating', 'int.integer')]), self.info(ParameterDoc([source]), source))
    def test_ambiguous_project_parameters_rejected(self):
        source = ParameterElement(1, 'Rating', 'string.text')
        dest = ParameterDoc([ParameterElement(2, 'Rating', 'string.text'), ParameterElement(3, 'Rating', 'string.text')])
        with self.assertRaises(ValueError): rules.map_parameter(dest, self.info(ParameterDoc([source]), source))
    def test_builtin_id_is_stable(self):
        self.assertEqual(rules.map_parameter(ParameterDoc([]), {'id': -100}).Value, -100)
    def test_transfer_remaps_rule_parameter(self):
        source = SharedParameterElement(1, 'Rating', 'string.text', 'GUID-1')
        target = SharedParameterElement(9, 'Rating', 'string.text', 'GUID-1')
        data = {'kind': 'rule', 'type': 'FilterStringRule', 'evaluator': 'FilterStringEquals',
                'parameter': self.info(ParameterDoc([source]), source), 'value': '120 min'}
        decoded = rules.decode_rule(ParameterDoc([target]), data, transfer=True)
        self.assertEqual(decoded.args[0].args[0].Value, 9)
        self.assertEqual(decoded.args[2], '120 min')
    def test_nested_groups_and_inversion(self):
        info = {'id': -100, 'name': 'Comments', 'storage': 'String'}
        data = rules.guided_rule(ParameterDoc([]), info, 'Does not equal', 'A')
        tree = {'kind': 'and', 'children': [data, {'kind': 'or', 'children': [data, data]}]}
        decoded = rules.decode_filter(ParameterDoc([]), tree)
        self.assertEqual(len(decoded.args[0]), 2)
        self.assertEqual(rules.count_rules(tree), 3)
    def test_empty_group_rejected(self):
        with self.assertRaises(ValueError): rules.decode_filter(ParameterDoc([]), {'kind': 'or', 'children': []})
    def test_numeric_text_operator_rejected(self):
        with self.assertRaises(ValueError): rules.guided_rule(ParameterDoc([]), {'id': 1, 'storage': 'Integer'}, 'Contains', '2')
    def test_arbitrary_instance_mapping_rejected(self):
        with self.assertRaises(ValueError):
            rules.map_element(ParameterDoc([]), {'id': 100, 'type': 'Autodesk.Revit.DB.Wall', 'name': 'Basic Wall'})


class BundleTests(unittest.TestCase):
    def test_python_syntax(self):
        for path in BUNDLE.rglob('*.py'):
            ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
    def test_xaml_events_exist(self):
        tree = ast.parse((BUNDLE / 'tpt_vfm/ui.py').read_text(encoding='utf-8'))
        classes = {n.name: n for n in tree.body if isinstance(n, ast.ClassDef)}
        for filename, cls in [('manager.xaml', 'ManagerWindow'), ('editor.xaml', 'EditorWindow'), ('transfer.xaml', 'TransferWindow'), ('report.xaml', 'ReportWindow'), ('rename.xaml', 'RenameWindow')]:
            methods = {n.name for n in classes[cls].body if isinstance(n, ast.FunctionDef)}
            for node in ET.parse(BUNDLE / filename).iter():
                for event in ('Click', 'SelectionChanged', 'TextChanged', 'Checked', 'SelectedItemChanged', 'PreviewMouseLeftButtonDown'):
                    if event in node.attrib:
                        self.assertIn(node.attrib[event], methods, filename + ': ' + node.attrib[event])


class CheckboxTreeTests(unittest.TestCase):
    def test_parent_checks_children(self):
        root = TreeItem('Root')
        a, b = root.add(TreeItem('A', 1)), root.add(TreeItem('B', 2))
        root.IsChecked = True
        self.assertEqual(checked([root]), [1, 2])
        self.assertTrue(a.IsChecked and b.IsChecked)
    def test_partial_parent_and_bubbling(self):
        root = TreeItem('Root')
        a, b = root.add(TreeItem('A', 1)), root.add(TreeItem('B', 2))
        a.IsChecked = True
        self.assertIsNone(root.IsChecked)
        b.IsChecked = True
        self.assertTrue(root.IsChecked)
        a.IsChecked = False
        self.assertIsNone(root.IsChecked)
    def test_group_clear_clears_all(self):
        root = TreeItem('Root')
        branch = root.add(TreeItem('Branch'))
        leaf = branch.add(TreeItem('Leaf', 3))
        root.IsChecked = True
        root.IsChecked = False
        self.assertEqual(checked([root]), [])
        self.assertFalse(leaf.IsChecked)
    def test_duplicate_view_deduplicated(self):
        roots = [TreeItem('First', 20), TreeItem('Second', 20)]
        for node in roots: node.IsChecked = True
        self.assertEqual(checked(roots, key=lambda x: x), [20])
    def test_role_filter_excludes_info(self):
        root = TreeItem('Root')
        root.add(TreeItem('Filter', 1, 'filter'))
        root.add(TreeItem('View', 2, 'view'))
        root.IsChecked = True
        self.assertEqual(checked([root], role='filter'), [1])
    def test_reference_category_report(self):
        total, rows = category_coverage([('Doors', {'Doors'}), ('Walls', {'Walls'})])
        self.assertEqual(total, 2)
        self.assertEqual(rows, [('Doors', ['Walls']), ('Walls', ['Doors'])])
    def test_single_category_report_no_false_missing(self):
        self.assertEqual(category_coverage([('Doors', {'Doors'})]), (1, [('Doors', [])]))
    def test_bulk_change_notifies_once(self):
        calls = []
        root = TreeItem('Root', changed=lambda: calls.append(1))
        for i in range(10): root.add(TreeItem(str(i), i, changed=lambda: calls.append(1)))
        root.IsChecked = True
        self.assertEqual(len(calls), 1)


class TransferBatchTests(unittest.TestCase):
    def test_filter_cache_reuses_committed_definition(self):
        target = FakeView(20, [])
        result = transfer.import_filter(FakeDoc([target]), types.SimpleNamespace(Id=ElementId(1)), 'rename', {1: ElementId(20)})
        self.assertIs(result, target)
    def test_failed_template_clears_uncommitted_mapping(self):
        src = FakeDoc([FakeView(1, []), FakeView(2, [])])
        dst = FakeDoc([])
        seen = []
        def fake_copy(source, destination, template, policy, cache):
            if template.Id.Value == 1:
                cache[99] = ElementId(999)
                raise ValueError('failed native copy')
            seen.append(dict(cache))
            return template
        plan = [{'id': i, 'view': str(i), 'status': 'ready'} for i in (1, 2)]
        with patch.object(transfer, 'copy_template', side_effect=fake_copy):
            result = transfer.execute(src, dst, plan, 'rename')
        self.assertEqual([r['status'] for r in result], ['failed', 'completed'])
        self.assertEqual(seen, [{}])


class GranularOverrideTests(unittest.TestCase):
    def test_line_weight_does_not_overwrite_colour_pattern(self):
        src, dst = Overrides(), Overrides()
        src.values.update(ProjectionLineWeight=7, ProjectionLineColor='red', ProjectionLinePatternId=99)
        dst.values.update(ProjectionLineWeight=2, ProjectionLineColor='blue', ProjectionLinePatternId=12)
        result = api.merge_overrides(src, dst, ['ProjectionLineWeight'])
        self.assertEqual(result.values, {'ProjectionLineWeight': 7, 'ProjectionLineColor': 'blue', 'ProjectionLinePatternId': 12})
    def test_fill_visibility_does_not_overwrite_pattern_colour(self):
        src, dst = Overrides(), Overrides()
        src.values.update(IsCutForegroundPatternVisible=False, CutForegroundPatternId=99)
        dst.values.update(IsCutForegroundPatternVisible=True, CutForegroundPatternId=12)
        result = api.merge_overrides(src, dst, ['IsCutForegroundPatternVisible'])
        self.assertFalse(result.IsCutForegroundPatternVisible)
        self.assertEqual(result.CutForegroundPatternId, 12)
    def test_revit_2026_api_members_exist(self):
        path = pathlib.Path(r'C:\Program Files\Autodesk\Revit 2026\RevitAPI.xml')
        if not path.exists(): self.skipTest('Installed Revit API XML not available')
        members = [n.attrib['name'] for n in ET.parse(path).getroot().find('members')]
        for names in api.GROUPS.values():
            for prop, setter in names:
                self.assertIn('P:Autodesk.Revit.DB.OverrideGraphicSettings.' + prop, members)
                self.assertTrue(any(x.startswith('M:Autodesk.Revit.DB.OverrideGraphicSettings.' + setter + '(') for x in members))
        for cls in ('FilterStringRule', 'FilterIntegerRule', 'FilterDoubleRule', 'FilterElementIdRule',
                    'FilterGlobalParameterAssociationRule', 'HasValueFilterRule', 'HasNoValueFilterRule'):
            self.assertTrue(any(x.startswith('M:Autodesk.Revit.DB.' + cls + '.#ctor(') for x in members))


class CheckboxInteractionTests(unittest.TestCase):
    def handler(self, control, modifiers):
        from tpt_vfm import selection
        tree = ast.parse((BUNDLE / 'tpt_vfm/ui.py').read_text(encoding='utf-8'))
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'checkbox_range_click')
        namespace = {'selection': selection, 'ListBox': FakeCheckList, 'TreeView': FakeCheckTree,
                     'VisualTreeHelper': types.SimpleNamespace(GetParent=lambda sender: control),
                     'Keyboard': types.SimpleNamespace(Modifiers=modifiers),
                     'ModifierKeys': types.SimpleNamespace(Shift=1)}
        exec(compile(ast.Module(body=[node], type_ignores=[]), '<interaction>', 'exec'), namespace)
        return namespace['checkbox_range_click']
    def test_list_toggle_then_shift_preserves_other_checks(self):
        items = [object() for _ in range(5)]
        control = FakeCheckList(items)
        control.SelectedItems.Add(items[4])
        window = types.SimpleNamespace()
        args = types.SimpleNamespace(Handled=False)
        self.handler(control, 2)(window, types.SimpleNamespace(DataContext=items[1]), args)
        self.assertTrue(args.Handled)
        self.assertEqual(control.SelectedItems, [items[4], items[1]])
        self.handler(control, 1)(window, types.SimpleNamespace(DataContext=items[3]), args)
        self.assertEqual(control.SelectedItems, [items[4], items[1], items[2], items[3]])
        self.handler(control, 2)(window, types.SimpleNamespace(DataContext=items[2]), args)
        self.assertNotIn(items[2], control.SelectedItems)
        self.assertIn(items[4], control.SelectedItems)
    def test_tree_shift_skips_collapsed_descendants(self):
        root = TreeItem('Root'); root.IsExpanded = True
        first = root.add(TreeItem('First')); branch = root.add(TreeItem('Collapsed'))
        hidden = branch.add(TreeItem('Hidden')); last = root.add(TreeItem('Last'))
        control = FakeCheckTree([root]); window = types.SimpleNamespace()
        args = types.SimpleNamespace(Handled=False)
        self.handler(control, 0)(window, types.SimpleNamespace(DataContext=first), args)
        self.handler(control, 1)(window, types.SimpleNamespace(DataContext=last), args)
        self.assertTrue(first.IsChecked)
        self.assertTrue(last.IsChecked)
        self.assertTrue(branch.IsChecked)
        self.assertTrue(hidden.IsChecked)  # Parent selection cascades intentionally.
        self.assertIs(window._check_anchors[control.GetHashCode()], first)

class FakeSelectedItems(list):
    def Contains(self, value): return value in self
    def Add(self, value): self.append(value)
    def Remove(self, value): self.remove(value)

class FakeCheckList:
    def __init__(self, items):
        self.Items = items
        self.SelectedItems = FakeSelectedItems()
    def GetHashCode(self): return id(self)

class FakeCheckTree:
    def __init__(self, items): self.Items = items
    def GetHashCode(self): return id(self)


class RangeSelectionTests(unittest.TestCase):
    def test_forward_inclusive_range(self):
        from tpt_vfm.selection import click_targets
        items = [object() for _ in range(5)]
        self.assertEqual(click_targets(items, items[3], items[1], True), items[1:4])
    def test_reverse_inclusive_range(self):
        from tpt_vfm.selection import click_targets
        items = [object() for _ in range(5)]
        self.assertEqual(click_targets(items, items[1], items[3], True), items[1:4])
    def test_stale_anchor_after_refresh(self):
        from tpt_vfm.selection import click_targets
        items = [object() for _ in range(3)]
        self.assertEqual(click_targets(items, items[1], object(), True), [items[1]])
    def test_ctrl_or_plain_targets_only_clicked_item(self):
        from tpt_vfm.selection import click_targets
        items = [object() for _ in range(3)]
        self.assertEqual(click_targets(items, items[2], items[0], False), [items[2]])
    def test_collapsed_tree_children_excluded(self):
        from tpt_vfm.selection import visible
        root = TreeItem('Root'); child = root.add(TreeItem('Child'))
        child.add(TreeItem('Hidden'))
        root.IsExpanded = True
        self.assertEqual(list(visible([root])), [root, child])

class BatchRenamePreviewTests(unittest.TestCase):
    def row(self, key, original, proposed, checked=True):
        return dict(id=key, original=original, proposed=proposed, checked=checked)
    def prepare(self, rows, inventory):
        from tpt_vfm.renaming import prepare
        return prepare(rows, inventory, lambda n: '/' not in n, lambda a,b: (a>b)-(a<b))
    def test_literal_replace_and_affixes(self):
        from tpt_vfm.renaming import transform
        self.assertEqual(transform('GWK_SuD', '_', '-', 'PRE_', '_POST', whole_words=False), 'PRE_GWK-SuD_POST')
    def test_case_sensitive_default(self):
        from tpt_vfm.renaming import transform
        self.assertEqual(transform('GWK_gwk', 'gwk', 'X'), 'GWK_X')
    def test_ignore_case_and_literal_replacement(self):
        from tpt_vfm.renaming import transform
        self.assertEqual(transform('A.a.A', 'a', r'\1', match_case=False), r'\1.\1.\1')
    def test_empty_find_unicode_and_underscores(self):
        from tpt_vfm.renaming import transform
        self.assertEqual(transform('Türen__', '', 'unused', 'Ä_', '_'), 'Ä_Türen___')
    def test_manual_name_checked_only(self):
        rows=[self.row(1,'A','Manual'),self.row(2,'B','Bad/',False)]
        errors, changes=self.prepare(rows,{1:'A',2:'B'})
        self.assertFalse(errors);self.assertEqual(changes,[rows[0]])
    def test_swap_is_valid(self):
        errors, changes=self.prepare([self.row(1,'A','B'),self.row(2,'B','A')],{1:'A',2:'B'})
        self.assertFalse(errors);self.assertEqual(len(changes),2)
    def test_duplicate_targets_marks_both_rows(self):
        errors,_=self.prepare([self.row(1,'A','X'),self.row(2,'B','X')],{1:'A',2:'B'})
        self.assertEqual(set(errors),{1,2})
    def test_conflict_with_unchecked_filter(self):
        errors,_=self.prepare([self.row(1,'A','B')],{1:'A',2:'B'})
        self.assertIn(1,errors)
    def test_blank_and_invalid_names(self):
        errors,_=self.prepare([self.row(1,'A','  '),self.row(2,'B','Bad/')],{1:'A',2:'B'})
        self.assertEqual(set(errors),{1,2})
    def test_deleted_and_changed_filters(self):
        errors,_=self.prepare([self.row(1,'A','X'),self.row(2,'B','Y')],{2:'Changed'})
        self.assertEqual(set(errors),{1,2})
    def test_unchanged_rows_not_committed(self):
        self.assertEqual(self.prepare([self.row(1,'A','A')],{1:'A'}),({},[]))
    def test_uses_supplied_revit_comparison(self):
        from tpt_vfm.renaming import prepare
        errors,_=prepare([self.row(1,'A','b')],{1:'A',2:'B'},lambda n:True,lambda a,b:0 if a.lower()==b.lower() else 1)
        self.assertIn(1,errors)

class BatchRenameDialogTests(unittest.TestCase):
    def method(self,name):
        from tpt_vfm import renaming, selection
        tree=ast.parse((BUNDLE/'tpt_vfm/ui.py').read_text(encoding='utf-8'))
        cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='RenameWindow')
        method=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name==name)
        method.decorator_list=[]
        namespace={'renaming':renaming,'selection':selection,'Keyboard':types.SimpleNamespace(Modifiers=0),'ModifierKeys':types.SimpleNamespace(Shift=1)}
        exec(compile(ast.Module(body=[method],type_ignores=[]),'<rename-dialog>','exec'),namespace)
        return namespace[name]
    def window(self):
        text=lambda value:types.SimpleNamespace(Text=value)
        return types.SimpleNamespace(rows=[types.SimpleNamespace(OriginalName='GWK_SuD',ProposedName='Manual',IsChecked=True),types.SimpleNamespace(OriginalName='Other',ProposedName='Keep manual',IsChecked=False)],
            rename_find=text('GWK'),rename_replace=text('TPT'),rename_prefix=text('P_'),rename_suffix=text('_S'),
            rename_match_case=types.SimpleNamespace(IsChecked=True),rename_whole_words=types.SimpleNamespace(IsChecked=True),_loading=False,_anchor=None,update=lambda:None)
    def test_repeated_preview_replaces_manual_edits_without_accumulating(self):
        window=self.window();preview=self.method('preview_click')
        preview(window,None,None);preview(window,None,None)
        self.assertEqual(window.rows[0].ProposedName,'P_TPT_SuD_S')
        self.assertEqual(window.rows[1].ProposedName,'Keep manual')
        self.assertFalse(window._loading)
    def test_reset_restores_all_rows_and_clears_fields(self):
        window=self.window();self.method('reset_click')(window,None,None)
        self.assertEqual([r.ProposedName for r in window.rows],['GWK_SuD','Other'])
        self.assertTrue(window.rows[0].IsChecked);self.assertFalse(window.rows[1].IsChecked)
        self.assertEqual(window.rename_prefix.Text,'');self.assertEqual(window.rename_find.Text,'')
        self.assertTrue(window.rename_match_case.IsChecked)
        self.assertTrue(window.rename_whole_words.IsChecked)
    def test_row_click_toggles_and_marks_event_handled(self):
        window=self.window();args=types.SimpleNamespace(Handled=False)
        self.method('row_mouse_down')(window,types.SimpleNamespace(DataContext=window.rows[0]),args)
        self.assertFalse(window.rows[0].IsChecked);self.assertTrue(args.Handled)
        self.assertIs(window._anchor,window.rows[0])

class WholeWordRenameTests(unittest.TestCase):
    def transform(self,name,**kwargs):
        from tpt_vfm.renaming import transform
        return transform(name,'Geschossdecke','Geschossdecken',**kwargs)
    def test_singular_changes_plural_stays(self):
        self.assertEqual(self.transform('Geschossdecke - Substrat'),'Geschossdecken - Substrat')
        self.assertEqual(self.transform('Geschossdecken - Innen'),'Geschossdecken - Innen')
    def test_underscore_and_punctuation_separators(self):
        for name in ('Geschossdecke_Innen','GWK_Geschossdecke','(Geschossdecke)','Geschossdecke-Innen','Geschossdecke/Innen'):
            self.assertEqual(self.transform(name),name.replace('Geschossdecke','Geschossdecken'))
    def test_embedded_word_and_digit_not_matched(self):
        for name in ('Geschossdecken','Geschossdeckenkante','XGeschossdecke','Geschossdecke2','2Geschossdecke'):
            self.assertEqual(self.transform(name),name)
    def test_partial_mode_remains_available(self):
        self.assertEqual(self.transform('Geschossdecken',whole_words=False),'Geschossdeckenn')
    def test_whole_word_ignore_case(self):
        self.assertEqual(self.transform('geschossdecke_geschossdecken',match_case=False),'Geschossdecken_geschossdecken')
    def test_unicode_letters_are_word_content(self):
        from tpt_vfm.renaming import transform
        self.assertEqual(transform('Türen_Türenrand_ÄTüren','Türen','Doors'),'Doors_Türenrand_ÄTüren')
    def test_literal_phrase_and_literal_replacement(self):
        from tpt_vfm.renaming import transform
        self.assertEqual(transform('A.B_A.BC','A.B',r'\1'),r'\1_A.BC')
    def test_multiple_matches_and_affixes(self):
        self.assertEqual(self.transform('Geschossdecke_Geschossdecke',prefix='P_',suffix='_S'),'P_Geschossdecken_Geschossdecken_S')
    def test_dialog_passes_partial_mode(self):
        fixture=BatchRenameDialogTests();window=fixture.window()
        window.rows[0].OriginalName='GWKSuD';window.rename_whole_words.IsChecked=False
        fixture.method('preview_click')(window,None,None)
        self.assertEqual(window.rows[0].ProposedName,'P_TPTSuD_S')

class RenameFixture:
    def __init__(self,key,name,doc=None): self.Id,self._name,self.doc=ElementId(key),name,doc
    @property
    def Name(self): return self._name
    @Name.setter
    def Name(self,value):
        if value=='FAIL': raise ValueError('Native setter failure')
        if any(f is not self and f.Name==value for f in self.doc.views.values()): raise ValueError('Duplicate native name')
        self._name=value

class BatchRenameTransactionTests(unittest.TestCase):
    def make_doc(self):
        doc=FakeDoc([RenameFixture(1,'A'),RenameFixture(2,'B')])
        for f in doc.views.values(): f.doc=doc
        return doc
    def apply(self,doc,rows):
        naming=types.SimpleNamespace(IsValidName=lambda n:'/' not in n,CompareNames=lambda a,b:(a>b)-(a<b))
        with patch.object(api.DB,'NamingUtils',naming,create=True),patch.object(api,'filters',side_effect=lambda d:list(d.views.values())):
            return api.batch_rename(doc,rows)
    def row(self,key,original,proposed):return dict(id=key,original=original,proposed=proposed,checked=True)
    def test_swap_uses_collision_free_temporaries(self):
        doc=self.make_doc()
        self.assertEqual(self.apply(doc,[self.row(1,'A','B'),self.row(2,'B','A')]),2)
        self.assertEqual([doc.views[i].Name for i in (1,2)],['B','A'])
    def test_native_failure_rolls_back_entire_batch(self):
        doc=self.make_doc()
        with self.assertRaises(ValueError): self.apply(doc,[self.row(1,'A','New'),self.row(2,'B','FAIL')])
        self.assertEqual([doc.views[i].Name for i in (1,2)],['A','B'])
    def test_fresh_inventory_blocks_stale_name(self):
        doc=self.make_doc();doc.views[1]._name='External'
        with self.assertRaises(ValueError):self.apply(doc,[self.row(1,'A','New')])
        self.assertEqual(doc.views[1].Name,'External')
    def test_unchecked_filter_untouched(self):
        doc=self.make_doc();row=self.row(2,'B','Ignored');row['checked']=False
        self.apply(doc,[self.row(1,'A','New'),row])
        self.assertEqual(doc.views[2].Name,'B')
    def test_readonly_document_blocked(self):
        doc=self.make_doc();doc.IsReadOnly=True
        with self.assertRaises(ValueError):self.apply(doc,[self.row(1,'A','New')])
        self.assertEqual(doc.views[1].Name,'A')

if __name__ == '__main__': unittest.main(verbosity=2)
