# -*- coding: utf-8 -*-
"""Lossless rule trees, guided editing and strict cross-document mapping."""
from vfm_host import DB
from System import Enum, Int32, Double
from System.Collections.Generic import List
from . import api


def parameter_info(doc, pid):
    value = api.eid(pid)
    result = {'id': value, 'name': str(value), 'guid': None, 'datatype': None,
              'storage': None, 'binding': None}
    if value < 0:
        bip = Enum.ToObject(DB.BuiltInParameter, value)
        try:
            result['name'] = DB.LabelUtils.GetLabelFor(bip)
            result['storage'] = str(doc.GetTypeOfStorage(DB.ParameterUtils.GetParameterTypeId(bip)))
        except Exception:
            pass
    else:
        pe = doc.GetElement(pid)
        if pe is None or not isinstance(pe, DB.ParameterElement):
            raise ValueError('Parameter {0} is missing.'.format(value))
        definition = pe.GetDefinition()
        result['name'] = definition.Name
        datatype = definition.GetDataType()
        result['datatype'] = datatype.TypeId
        if isinstance(pe, DB.SharedParameterElement):
            result['guid'] = str(pe.GuidValue)
        text = datatype.TypeId.lower()
        if 'string' in text:
            result['storage'] = 'String'
        elif 'int' in text or 'boolean' in text:
            result['storage'] = 'Integer'
        elif 'reference' in text or DB.Category.IsBuiltInCategory(datatype):
            result['storage'] = 'ElementId'
        else:
            result['storage'] = 'Double'
        binding = doc.ParameterBindings.get_Item(definition)
        if binding is not None:
            result['binding'] = binding.GetType().Name
    return result


def common_parameters(doc, categories):
    values = DB.ParameterFilterUtilities.GetFilterableParametersInCommon(doc, api.ids(categories))
    infos = [parameter_info(doc, pid) for pid in values]
    unknown = dict((x['id'], x) for x in infos if x['id'] < 0)
    # A built-in parameter's storage type is available without an element,
    # but its unit spec is obtained from an actual parameter definition.
    for cid in categories:
        for collector in (DB.FilteredElementCollector(doc).OfCategoryId(cid).WhereElementIsNotElementType(),
                          DB.FilteredElementCollector(doc).OfCategoryId(cid).WhereElementIsElementType()):
            for index, element in enumerate(collector):
                if index >= 20 or not unknown:
                    break
                for value in list(unknown.keys()):
                    p = element.get_Parameter(Enum.ToObject(DB.BuiltInParameter, value))
                    if p is not None:
                        unknown[value]['datatype'] = p.Definition.GetDataType().TypeId
                        del unknown[value]
        if not unknown:
            break
    return sorted(infos, key=lambda x: (x['name'].lower(), x['id']))


def element_ref(doc, element_id):
    value = api.eid(element_id)
    result = {'id': value}
    if value >= 0:
        element = doc.GetElement(element_id)
        if element is None:
            raise ValueError('Referenced element {0} is missing.'.format(value))
        result.update(name=api.name(element), type=element.GetType().FullName,
                      category=api.eid(element.Category.Id) if element.Category else None)
        if isinstance(element, DB.ElementType):
            result['family'] = element.FamilyName
        if isinstance(element, DB.GlobalParameter):
            result['datatype'] = element.GetDefinition().GetDataType().TypeId
    return result


def encode_rule(doc, rule):
    kind = rule.GetType().Name
    if kind == 'FilterInverseRule':
        return {'kind': 'inverse', 'rule': encode_rule(doc, rule.GetInnerRule())}
    if kind == 'FilterCategoryRule':
        return {'kind': 'category', 'categories': [api.eid(x) for x in rule.GetCategories()]}
    if kind == 'SharedParameterApplicableRule':
        return {'kind': 'applicable', 'name': rule.ParameterName}
    supported = ('FilterStringRule', 'FilterIntegerRule', 'FilterDoubleRule',
                 'FilterElementIdRule', 'FilterGlobalParameterAssociationRule',
                 'HasValueFilterRule', 'HasNoValueFilterRule')
    if kind not in supported:
        raise ValueError('Unsupported rule type: {0}. Existing rules remain unchanged.'.format(kind))
    result = {'kind': 'rule', 'type': kind, 'parameter': parameter_info(doc, rule.GetRuleParameter())}
    if hasattr(rule, 'GetEvaluator'):
        result['evaluator'] = rule.GetEvaluator().GetType().Name
    if kind == 'FilterStringRule':
        result['value'] = rule.RuleString
    elif kind in ('FilterElementIdRule', 'FilterGlobalParameterAssociationRule'):
        result['value'] = element_ref(doc, rule.RuleValue)
    elif kind in ('FilterIntegerRule', 'FilterDoubleRule'):
        result['value'] = float(rule.RuleValue) if kind == 'FilterDoubleRule' else int(rule.RuleValue)
        if kind == 'FilterIntegerRule' and api.eid(rule.GetRuleParameter()) == int(DB.BuiltInParameter.ELEM_PARTITION_PARAM):
            workset = doc.GetWorksetTable().GetWorkset(DB.WorksetId(int(rule.RuleValue)))
            if workset is not None:
                result['workset'] = {'name': workset.Name, 'kind': str(workset.Kind)}
        if kind == 'FilterDoubleRule':
            result['epsilon'] = rule.Epsilon
    return result


def encode_filter(doc, element_filter):
    if element_filter is None:
        return None
    kind = element_filter.GetType().Name
    if kind in ('LogicalAndFilter', 'LogicalOrFilter'):
        return {'kind': 'and' if kind == 'LogicalAndFilter' else 'or',
                'children': [encode_filter(doc, x) for x in element_filter.GetFilters()]}
    if kind == 'ElementParameterFilter':
        return {'kind': 'parameters', 'inverted': bool(element_filter.Inverted),
                'children': [encode_rule(doc, r) for r in element_filter.GetRules()]}
    raise ValueError('Unsupported filter tree node: ' + kind)


def map_parameter(destination, info):
    if info['id'] < 0:
        return DB.ElementId(info['id'])
    candidates = list(DB.FilteredElementCollector(destination).OfClass(DB.ParameterElement))
    if info.get('guid'):
        candidates = [x for x in candidates if isinstance(x, DB.SharedParameterElement)
                      and str(x.GuidValue).lower() == info['guid'].lower()]
    else:
        candidates = [x for x in candidates if not isinstance(x, DB.SharedParameterElement)
                      and x.GetDefinition().Name == info['name']]
    candidates = [x for x in candidates if x.GetDefinition().GetDataType().TypeId == info['datatype']]
    if info.get('binding'):
        candidates = [x for x in candidates if parameter_info(destination, x.Id).get('binding') == info['binding']]
    if len(candidates) != 1:
        raise ValueError('Parameter "{0}" has {1} compatible matches. Bind the same shared GUID or a unique project parameter with matching data type and binding first.'.format(info['name'], len(candidates)))
    return candidates[0].Id


def map_element(destination, reference):
    if reference['id'] < 0:
        return DB.ElementId(reference['id'])
    # Only stable named definitions are transferable, never arbitrary instances.
    cls = reference.get('type', '').split('.')[-1]
    allowed = ('Material', 'Level', 'Phase', 'Workset', 'GlobalParameter',
               'FillPatternElement', 'LinePatternElement')
    if cls not in allowed and 'family' not in reference:
        raise ValueError('An element-id rule references an instance. Remap it in the destination project before transfer.')
    matches = []
    for element in DB.FilteredElementCollector(destination).WhereElementIsNotElementType():
        if element.GetType().FullName == reference['type'] and api.name(element) == reference['name']:
            matches.append(element)
    if 'family' in reference:
        matches = [x for x in DB.FilteredElementCollector(destination).WhereElementIsElementType()
                   if x.GetType().FullName == reference['type'] and api.name(x) == reference['name']
                   and x.FamilyName == reference['family']
                   and (api.eid(x.Category.Id) if x.Category else None) == reference.get('category')]
    if cls == 'GlobalParameter':
        matches = [x for x in matches if x.GetDefinition().GetDataType().TypeId == reference.get('datatype')]
    if len(matches) != 1:
        raise ValueError('Referenced {0} "{1}" has {2} matches in destination.'.format(cls, reference.get('name'), len(matches)))
    return matches[0].Id


def decode_rule(doc, data, transfer=False):
    kind = data['kind']
    if kind == 'inverse':
        return DB.FilterInverseRule(decode_rule(doc, data['rule'], transfer))
    if kind == 'category':
        return DB.FilterCategoryRule(api.ids([DB.ElementId(x) for x in data['categories']]))
    if kind == 'applicable':
        return DB.SharedParameterApplicableRule(data['name'])
    info = data['parameter']
    pid = map_parameter(doc, info) if transfer else DB.ElementId(info['id'])
    cls = getattr(DB, data['type'])
    if data['type'] in ('HasValueFilterRule', 'HasNoValueFilterRule'):
        return cls(pid)
    provider = DB.ParameterValueProvider(pid)
    evaluator = getattr(DB, data['evaluator'])()
    value = data['value']
    if data['type'] == 'FilterStringRule':
        return cls(provider, evaluator, value)
    if data['type'] == 'FilterDoubleRule':
        return cls(provider, evaluator, Double(value), Double(data['epsilon']))
    if data['type'] == 'FilterIntegerRule':
        if transfer and data.get('workset'):
            matches = [x for x in DB.FilteredWorksetCollector(doc)
                       if x.Name == data['workset']['name'] and str(x.Kind) == data['workset']['kind']]
            if len(matches) != 1:
                raise ValueError('Workset "{0}" is missing or ambiguous in destination.'.format(data['workset']['name']))
            value = matches[0].Id.IntegerValue
        return cls(provider, evaluator, Int32(value))
    ref = map_element(doc, value) if transfer else DB.ElementId(value['id'])
    return cls(provider, evaluator, ref)


def decode_filter(doc, data, transfer=False):
    if data is None:
        return None
    kind = data['kind']
    if kind in ('and', 'or'):
        children = [decode_filter(doc, x, transfer) for x in data['children']]
        if not children or any(x is None for x in children):
            raise ValueError('AND/OR groups must contain at least one rule or group.')
        if len(children) == 1:
            return children[0]
        cls = DB.LogicalAndFilter if kind == 'and' else DB.LogicalOrFilter
        return cls(List[DB.ElementFilter](children))
    if kind == 'parameters':
        children = [decode_rule(doc, x, transfer) for x in data['children']]
        if not children:
            raise ValueError('A parameter group is empty.')
        return DB.ElementParameterFilter(List[DB.FilterRule](children), data.get('inverted', False))
    return DB.ElementParameterFilter(decode_rule(doc, data, transfer))


def count_rules(data):
    if data is None:
        return 0
    if data['kind'] in ('and', 'or', 'parameters'):
        return sum(count_rules(x) for x in data['children'])
    if data['kind'] == 'inverse':
        return count_rules(data['rule'])
    return 1


def describe(data):
    kind = data['kind']
    if kind in ('and', 'or'):
        return kind.upper() + ' group'
    if kind == 'parameters':
        return ('NOT ' if data.get('inverted') else '') + 'All parameter rules'
    if kind == 'inverse':
        return 'NOT (' + describe(data['rule']) + ')'
    if kind == 'category':
        return 'Category rule: ' + ', '.join(str(x) for x in data['categories'])
    if kind == 'applicable':
        return 'Supports shared parameter: ' + data['name']
    value = data.get('value', '')
    if isinstance(value, dict):
        value = value.get('name', value.get('id'))
    evaluator = data.get('evaluator', data['type']).replace('FilterString', '').replace('FilterNumeric', '').replace('Filter', '').replace('Rule', '')
    return '{0} | {1} | {2}'.format(data['parameter']['name'], evaluator, value)


def guided_rule(doc, info, operator, text):
    kind = info['storage']
    data = {'kind': 'rule', 'parameter': info}
    if operator in ('Has value', 'Has no value'):
        data['type'] = 'HasValueFilterRule' if operator == 'Has value' else 'HasNoValueFilterRule'
        return data
    operators = {'Equals': 'Equals', 'Does not equal': 'Equals', 'Greater than': 'Greater',
                 'Greater or equal': 'GreaterOrEqual', 'Less than': 'Less',
                 'Less or equal': 'LessOrEqual', 'Contains': 'Contains',
                 'Begins with': 'BeginsWith', 'Ends with': 'EndsWith'}
    if kind != 'String' and operator in ('Contains', 'Begins with', 'Ends with'):
        raise ValueError('This operator requires a text parameter.')
    if kind == 'String':
        data.update(type='FilterStringRule', evaluator='FilterString' + operators[operator], value=text)
    elif kind == 'Integer':
        data.update(type='FilterIntegerRule', evaluator='FilterNumeric' + operators[operator], value=int(text))
    elif kind == 'Double':
        # Project units are used when the parameter spec is known; explicit
        # internal: prefix is available for dimensionless/built-in specs.
        number = None
        datatype = info.get('datatype')
        if text.lower().startswith('internal:'):
            number = float(text.split(':', 1)[1].strip())
        elif datatype and DB.UnitUtils.IsMeasurableSpec(DB.ForgeTypeId(datatype)):
            import clr
            output = clr.Reference[Double]()
            if DB.UnitFormatUtils.TryParse(doc.GetUnits(), DB.ForgeTypeId(datatype), text, output):
                number = output.Value
            else:
                raise ValueError('Cannot read this value in project units. Include a unit suffix such as mm or m.')
        elif datatype:
            number = float(text)
        else:
            raise ValueError('For this numeric parameter enter internal:<value> using Revit internal units (feet for length).')
        data.update(type='FilterDoubleRule', evaluator='FilterNumeric' + operators[operator],
                    value=number, epsilon=1e-9)
    elif kind == 'ElementId':
        data.update(type='FilterElementIdRule', evaluator='FilterNumeric' + operators[operator],
                    value=element_ref(doc, DB.ElementId(int(text))))
    else:
        raise ValueError('Parameter storage type is unavailable.')
    return {'kind': 'inverse', 'rule': data} if operator == 'Does not equal' else data


def save_filter(doc, existing, proposed, categories, tree):
    api.ensure_writable(doc)
    element_filter = decode_filter(doc, tree)
    category_ids = api.ids(categories)
    if not categories:
        raise ValueError('Select at least one category.')
    if element_filter is not None and not DB.ParameterFilterElement.AllRuleParametersApplicable(doc, category_ids, element_filter):
        raise ValueError('A rule parameter is not applicable to the selected categories.')
    def save():
        target = existing
        if target is None:
            target = DB.ParameterFilterElement.Create(doc, proposed, category_ids)
        else:
            target.ClearRules()
            target.SetCategories(category_ids)
            target.Name = proposed
        if element_filter is not None:
            target.SetElementFilter(element_filter)
        return target
    return api.transaction(doc, 'View Filter Manager - edit rules', save)
