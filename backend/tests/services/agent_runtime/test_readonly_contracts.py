"""Readonly request contracts without tenant provisioning or connections."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.agent_control import TaskControl
from app.schemas.agent_runtime import (
    MessageHistoryQuery,
    ReadonlyCheckpointCreate,
    RuntimeEventCreate,
    RuntimeResultCreate,
)


def test_output_dtos_bound_typed_content_and_forbid_asserted_identity():
    receipt_ids = [uuid4()]
    result = {'idempotency_key': 'result', 'receipt_ids': receipt_ids, 'payload': {'support': ['Evidence']}}
    event = {'idempotency_key': 'event', 'receipt_ids': receipt_ids, 'payload': {'stage': 'D4'},
             'event_type': 'query_completed'}
    progress = {**event, 'event_type': 'progress', 'receipt_ids': []}
    for cls, body in ((RuntimeResultCreate, result), (RuntimeEventCreate, event)):
        assert cls.model_validate(body)
        for field in ('actor_id', 'data_class', 'projection_id', 'projection_digest', 'source_capa_id', 'run_id'):
            with pytest.raises(ValidationError):
                cls.model_validate({**body, field: 'spoof'})
        for changes in ({'idempotency_key': ''}, {'idempotency_key': 'x'*101},
                        {'receipt_ids': [uuid4() for _ in range(21)]}, {'receipt_ids': ['bad']}):
            with pytest.raises(ValidationError):
                cls.model_validate({**body, **changes})
        with pytest.raises(ValidationError):
            cls.model_validate({**body, 'payload': {**body['payload'], 'unbounded': 'bad'}})
    for payload in ({'explanations': ['x'*2001]}, {'support': ['x']*21}, {'support': [123]}, {'explanations': 'bad'}):
        with pytest.raises(ValidationError):
            RuntimeResultCreate.model_validate({**result, 'payload': payload})
    with pytest.raises(ValidationError):
        RuntimeResultCreate.model_validate({**result, 'receipt_ids': []})
    with pytest.raises(ValidationError):
        RuntimeEventCreate.model_validate({**event, 'receipt_ids': []})
    assert RuntimeEventCreate.model_validate(progress)
    for payload in ({'message': 'x'*1001}, {'completed': True}, {'completed': -1}, {'stage': 7}):
        with pytest.raises(ValidationError):
            RuntimeEventCreate.model_validate({**progress, 'payload': payload})


def test_strict_checkpoint_history_restart_contracts():
    valid = dict(idempotency_key='key', receipt_ids=[uuid4()])
    assert ReadonlyCheckpointCreate(**valid)
    for fields in ({'receipt_ids': []}, {'receipt_ids': [uuid4() for _ in range(21)]},
                   {'idempotency_key': ''}, {'idempotency_key': 7}, {'idempotency_key': 'x'*101}):
        with pytest.raises(ValidationError):
            ReadonlyCheckpointCreate(**{**valid, **fields})
    for name in ('watermark', 'accepted_message_seq', 'digest', 'tenant_generation', 'lease_epoch', 'memory', 'target_capa_id'):
        with pytest.raises(ValidationError):
            ReadonlyCheckpointCreate(**valid, **{name: 'spoof'})
    for fields in ({'after_sequence': True}, {'after_sequence': '1'}, {'after_sequence': -1}, {'limit': 21}, {'limit': '1'}):
        with pytest.raises(ValidationError):
            MessageHistoryQuery(**fields)
    base = dict(run_id=uuid4(), expected_epoch=1, idempotency_key='key', checkpoint_id=uuid4())
    assert TaskControl(action='restart', **base)
    for action in ('pause', 'resume', 'cancel'):
        with pytest.raises(ValidationError):
            TaskControl(action=action, **base)
