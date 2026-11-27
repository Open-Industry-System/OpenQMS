"""Narrow synchronous runtime clients. Closing never changes remote state."""
from . import _codec
from ._deadline import Deadline
from ._transport import Transport
from .errors import ClientClosed, HTTPError, ResponseTooLarge, SDKError, UnknownOutcome
from .models import (
    PfmeaImpactAnalysis, PfmeaImpactAssessment, PfmeaImpactConfirmation,
    PfmeaImpactRelease, PfmeaImpactResultRef,
)


_DEFINITE_REJECTIONS = frozenset({400, 401, 403, 404, 409, 410, 422})


def _call(parent, operation, parameters, *, run=None, **context):
    deadline = Deadline(parent._config.timeout, operation)
    if parent._closed or (run is not None and run.state != 'open'):
        raise ClientClosed(operation, kind='client_closed')
    sent = False
    status = None
    failure = None
    try:
        request = _codec.encode_request(operation, parameters)
        deadline.check()
        response = parent._transport.exchange(
            operation, token=None if run is None else run._token,
            request=request, deadline=deadline)
        sent = response.may_have_been_sent
        status = response.status
        deadline.check()
        if not 200 <= status < 300:
            raise HTTPError(operation, kind='http_status', status=status,
                            may_have_been_sent=sent)
        if len(response.body) > parent._config.response_budget:
            raise ResponseTooLarge(operation, kind='response_too_large',
                                   status=status, may_have_been_sent=sent)
        result = _codec.decode_response(operation, response.body, **context)
        deadline.check()
        return result
    except SDKError as error:
        # Copy only bounded safe metadata, never retain an exception or body.
        sent = sent or error.may_have_been_sent
        status = error.status if error.status is not None else status
        cls, kind = type(error), error.kind
        unknown = operation == 'finish' and sent and not (
            isinstance(error, HTTPError) and status in _DEFINITE_REJECTIONS)
        if unknown:
            cls, kind = UnknownOutcome, 'outcome_unknown'
            run._state = 'uncertain'
            run._token = None
        failure = (cls, kind, status, sent, error.outcome_unknown or unknown)
    cls, kind, status, sent, unknown = failure
    raise cls(operation, kind=kind, status=status,
              may_have_been_sent=sent, outcome_unknown=unknown) from None


class InstallationClient:
    """Own the transport; keep this parent alive while using borrowed runs."""

    def __init__(self, config, installation_id, secret):
        self._config = config
        self._installation_id = installation_id
        self._secret = secret
        self._transport = Transport(config)
        self._closed = False

    def claim_run(self, *, request_key):
        envelope = _call(self, 'claim', dict(
            installation_id=self._installation_id, secret=self._secret,
            request_key=request_key))
        return RunClient(self, envelope)

    def close(self):
        if not self._closed:
            self._closed = True
            self._secret = None
            self._transport.close()


class RunClient:
    """Borrow the parent's transport; claim metadata never contains the token.

    close() is local only. Dropping credential references is not secure erasure.
    An uncertain finish is never retried or resolved by querying another API.
    """

    def __init__(self, parent, envelope):
        self._parent = parent
        self._claim = envelope.claim
        self._token = envelope.token
        self._state = 'open'
        self._owns_parent = False

    @classmethod
    def from_launch(cls, launch):
        from .models import ManagedLaunch, RunClaim, ClientConfig
        from .errors import ConfigError
        if type(launch) is not ManagedLaunch:
            raise ConfigError('config',kind='invalid_type')
        launch.__post_init__()
        config=ClientConfig(launch.api_origin,tenant_slug=launch.tenant_slug,timeout=30)
        owner=_ManagedOwner(config,launch)
        run=cls.__new__(cls)
        run._parent=owner
        run._claim=RunClaim(launch.run_id,launch.task_id,launch.lease_epoch,launch.lease_expires_at,
            launch.accepted_message_seq,launch.has_resume_checkpoint)
        run._token=launch.token
        run._state='open'
        run._owns_parent=True
        return run

    def __enter__(self):
        if self._state!='open': raise ClientClosed('close',kind='client_closed')
        return self

    def __exit__(self,*args):
        self.close()

    @property
    def claim(self):
        return self._claim

    @property
    def state(self):
        return self._state

    def _call(self, operation, parameters, **context):
        return _call(self._parent, operation, parameters, run=self,
                     run_id=self._claim.run_id, task_id=self._claim.task_id,
                     **context)

    def capabilities(self):
        return self._call('capabilities', {})

    def claim_messages(self, *, limit=20):
        return self._call('claim_messages', dict(limit=limit))

    def ack_messages(self, *, batch_id, through_sequence):
        return self._call('ack_messages', dict(batch_id=batch_id, through_sequence=through_sequence))

    def get_capa_context(self, *, report_id=None, view='report'):
        return self._call('capa_context', dict(report_id=report_id, view=view),
                          report_id=report_id, view=view)

    def record_event(self, *, idempotency_key, event_type, payload, receipt_ids=()):
        return self._call('record_event', dict(idempotency_key=idempotency_key,
                          event_type=event_type, payload=payload, receipt_ids=receipt_ids))

    def save_result(self, *, idempotency_key, payload, receipt_ids):
        return self._call('save_result', dict(idempotency_key=idempotency_key,
                          payload=payload, receipt_ids=receipt_ids))

    def save_checkpoint(self, *, idempotency_key, receipt_ids):
        return self._call('save_checkpoint', dict(idempotency_key=idempotency_key,
                          receipt_ids=receipt_ids))

    def message_history(self, *, after_sequence=0, limit=20):
        return self._call('message_history', dict(after_sequence=after_sequence, limit=limit))

    def model_turn(self, *, turn=0):
        return self._call('model_turn',dict(turn=turn))

    def model_tool(self, *, call_id):
        return self._call('model_tool',dict(call_id=call_id))

    def save_d4_checkpoint(self):
        return self._call('save_d4_checkpoint',{})

    def save_d4_candidate(self, *, command_key, text, supporting=(), opposing=(),
                          missing_information=(), operation='save', predecessor_id=None,
                          correction_message_id=None):
        return self._call('save_d4_candidate', dict(command_key=command_key, text=text,
            supporting=supporting, opposing=opposing, missing_information=missing_information,
            operation=operation, predecessor_id=predecessor_id, correction_message_id=correction_message_id))

    def _call_pfmea(self, operation, parameters, **context):
        return self._call(operation, parameters, lease_epoch=self._claim.lease_epoch, **context)

    def pfmea_impact_material(self) -> PfmeaImpactRelease:
        """Read the current run's approved CAPA assessment material."""
        return self._call_pfmea('pfmea_impact_material', {})

    def pfmea_impact_search(
        self, *, term: str, snapshot_digest: str, cursor: str | None = None,
    ) -> PfmeaImpactRelease:
        """Search only the run's fixed target. Cursors are supplied by the server."""
        from ._pfmea import expected_snapshot
        operation = 'pfmea_impact_search'
        return self._call_pfmea(operation, dict(term=term, cursor=cursor),
                                snapshot_digest=expected_snapshot(operation, snapshot_digest))

    def pfmea_impact_page(
        self, *, scope_ref: str, snapshot_digest: str, cursor: str | None = None,
    ) -> PfmeaImpactRelease:
        """Fetch and verify a page; verification does not acknowledge receipt."""
        from ._pfmea import expected_snapshot
        operation = 'pfmea_impact_page'
        return self._call_pfmea(operation, dict(scope_ref=scope_ref, cursor=cursor),
                                scope_ref=scope_ref, snapshot_digest=expected_snapshot(operation, snapshot_digest))

    def pfmea_impact_confirm(self, page: PfmeaImpactRelease) -> PfmeaImpactConfirmation:
        """Explicitly acknowledge the verified bytes of a canonical page."""
        from ._pfmea import confirmation_parameters
        operation = 'pfmea_impact_confirm'
        if self._parent._closed or self._state != 'open':
            raise ClientClosed(operation, kind='client_closed')
        return self._call_pfmea(operation, confirmation_parameters(page, self._claim))

    def pfmea_impact_submit(
        self, *, operation_key: str, analyses: tuple[PfmeaImpactAnalysis, ...],
        assessments: tuple[PfmeaImpactAssessment, ...],
    ) -> PfmeaImpactResultRef:
        """Submit a bounded proposal; retain the same key on explicit replay."""
        return self._call_pfmea('pfmea_impact_result', dict(
            operation_key=operation_key, analyses=analyses, assessments=assessments,
        ))

    def finish(self, *, status):
        result = self._call('finish', dict(status=status), finish_status=status)
        self._state = 'closed_successfully'
        self._token = None
        return result

    def close(self):
        self._state = 'closed'
        self._token = None
        if self._owns_parent:
            self._parent.close()


class _ManagedOwner:
    def __init__(self,config,launch):
        self._config=config
        self._transport=Transport(config,launch=launch)
        self._closed=False

    def close(self):
        if not self._closed:
            self._closed=True
            self._transport.close()
