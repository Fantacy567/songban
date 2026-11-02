"""Additive E1 contract; preserves the frozen P0 and runtime base JSON files."""
from copy import deepcopy

_id = {'type': 'string', 'minLength': 1, 'maxLength': 100}
_revision = {'type': 'integer', 'minimum': 0}
_time = {'anyOf': [{'type': 'string', 'format': 'date-time'}, {'type': 'null'}]}
_texts = {'type': 'array', 'items': {'type': 'string', 'minLength': 1, 'maxLength': 60}, 'maxItems': 6}


def _object(properties):
    return {'type': 'object', 'additionalProperties': False, 'properties': properties, 'required': list(properties)}


ENTRY_SCHEMAS = {
    'EntryCandidate': _object({'source_domain': {'const': 'core_interview'},
                              'source_version': {'type': 'integer', 'minimum': 1},
                              'source_confirmed_at': {'type': 'string', 'format': 'date-time'},
                              'goals': _texts, 'experiences': _texts}),
    'LearningEntry': _object({'id': _id, 'revision': _revision, 'learner_id': _id,
                             'status': {'type': 'string', 'enum': ['none', 'offered', 'confirmed', 'declined']},
                             'goals': _texts, 'experiences': _texts,
                             'source_domain': {'anyOf': [{'const': 'core_interview'}, {'type': 'null'}]},
                             'source_version': {'anyOf': [{'type': 'integer', 'minimum': 1}, {'type': 'null'}]},
                             'source_confirmed_at': _time, 'offered_at': _time, 'confirmed_at': _time,
                             'candidate': {'anyOf': [{'$ref': '#/components/schemas/EntryCandidate'}, {'type': 'null'}]}}),
    'SaveLearningEntry': _object({'request_id': {'type': 'string', 'minLength': 8, 'maxLength': 100},
                                 'expected_revision': _revision, 'source_version': {'type': 'integer', 'minimum': 1},
                                 'subject_confirmed': {'const': True},
                                 'selected_fields': {'type': 'array', 'items': {'type': 'string', 'enum': ['goals', 'experiences']},
                                                     'minItems': 1, 'maxItems': 2, 'uniqueItems': True}}),
    'ConfirmLearningEntry': _object({'request_id': {'type': 'string', 'minLength': 8, 'maxLength': 100},
                                    'expected_revision': _revision,
                                    'decision': {'type': 'string', 'enum': ['accept', 'decline']}}),
}


def _operation(op, summary, request_schema=None):
    spec = {'operationId': op, 'summary': summary,
            'parameters': [{'name': 'learner_id', 'in': 'path', 'required': True, 'schema': _id}],
            'security': [{'ScopedSession': []}],
            'responses': {'200': {'description': '本人入口摘要', 'content': {'application/json': {'schema': {'$ref': '#/components/schemas/LearningEntry'}}}},
                          'default': {'description': '鉴权、版本或请求错误', 'content': {'application/json': {'schema': {'$ref': '#/components/schemas/Error'}}}}}}
    if request_schema:
        spec['parameters'].append({'name': 'X-CSRF-Token', 'in': 'header', 'required': True, 'schema': _id})
        spec['requestBody'] = {'required': True, 'content': {'application/json': {'schema': {'$ref': '#/components/schemas/' + request_schema}}}}
    return spec


ENTRY_PATHS = {
    '/learners/{learner_id}/entry': {
        'get': _operation('entry', '读取本人已映射摘要；仅管理者可预览其本人来源'),
        'post': _operation('saveEntry', '管理者明确关联并提供最小访谈摘要', 'SaveLearningEntry'),
    },
    '/learners/{learner_id}/entry/confirm': {
        'post': _operation('confirmEntry', '孩子选择采用或暂不采用摘要', 'ConfirmLearningEntry'),
    },
}


def install_entry_contract(contract):
    contract.schemas.update(deepcopy(ENTRY_SCHEMAS))
    contract.document['paths'].update(deepcopy(ENTRY_PATHS))
