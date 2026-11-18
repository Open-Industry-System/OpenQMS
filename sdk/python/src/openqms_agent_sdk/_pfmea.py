"""Bounded R7 codec invoked only for the fixed PFMEA runtime routes."""
import base64
from binascii import Error as Base64Error
from hashlib import sha256
from hmac import compare_digest

from . import models
from ._codec import _Invalid, _array, _digest, _enum, _integer, _object, _parse, _require, _text, _uuid
from .errors import ValidationError


MAX_BYTES = 256 * 1024
MAX_TEXT_BYTES = 16 * 1024
_MAX_B64_LENGTH = ((MAX_BYTES + 2) // 3) * 4
_MAX_HANDLE = 4096
_CONCLUSIONS = ("impact_found", "no_impact_found", "insufficient_evidence")
_RELEASE_KEYS = {
    "run_id", "task_id", "lease_epoch", "receipt_id", "projection_bytes",
    "payload_digest", "snapshot_digest", "scope_ref", "page_key", "confirmation_token", "next_cursor",
}


def _bounded_text(value, limit=MAX_TEXT_BYTES, *, required=False):
    text = _text(value, int(required), limit)
    _require("\x00" not in text and len(text.encode("utf-8")) <= limit, "invalid_value")
    _require(not required or bool(text.strip()), "invalid_value")
    return text


def _handle(value):
    text = _text(value, 1, _MAX_HANDLE)
    _require(text.isascii() and all(33 <= ord(char) <= 126 for char in text), "invalid_value")
    return text


def _cursor(value):
    return None if value is None else _handle(value)


def _tuple(value, minimum, maximum):
    _require(type(value) is tuple, "invalid_type")
    return _array(value, minimum, maximum, request=True)


def _refs(values):
    return [_bounded_text(value, required=True) for value in _tuple(values, 0, 256)]


def _analysis(value):
    _require(type(value) is models.PfmeaImpactAnalysis, "invalid_type")
    return {
        "analysis_ref": _bounded_text(value.analysis_ref, required=True),
        "reason": _bounded_text(value.reason, required=True),
        "fact_refs": _refs(value.fact_refs),
        "inference": _bounded_text(value.inference),
    }


def _adjustment(value):
    _require(type(value) is models.PfmeaImpactAdjustment, "invalid_type")
    return {"target_ref": _bounded_text(value.target_ref, required=True),
            "proposal": _bounded_text(value.proposal, required=True)}


def _assessment(value):
    _require(type(value) is models.PfmeaImpactAssessment, "invalid_type")
    return {
        "measure_id": str(_uuid(value.measure_id)),
        "formal_revision": None if value.formal_revision is None else str(_uuid(value.formal_revision)),
        "analysis_ref": _bounded_text(value.analysis_ref, required=True),
        "conclusion": _enum(value.conclusion, _CONCLUSIONS),
        "evidence_refs": _refs(value.evidence_refs),
        "coverage_refs": _refs(value.coverage_refs),
        "exclusion_refs": _refs(value.exclusion_refs),
        "missing_information": _refs(value.missing_information),
        "node_adjustments": [_adjustment(item) for item in _tuple(value.node_adjustments, 0, 256)],
    }


def encode_body(operation, parameters):
    p = parameters
    if operation == "pfmea_impact_search":
        return {"term": _bounded_text(p["term"], 120, required=True), "cursor": _cursor(p.get("cursor"))}
    if operation == "pfmea_impact_page":
        return {"scope_ref": _handle(p["scope_ref"]), "cursor": _cursor(p.get("cursor"))}
    if operation == "pfmea_impact_confirm":
        return {"release_id": str(_uuid(p["release_id"])), "page_key": _digest(p["page_key"]),
                "payload_digest": _digest(p["payload_digest"]), "token": _digest(p["token"])}
    _require(operation == "pfmea_impact_result", "invalid_request")
    return {
        "operation_key": _bounded_text(p["operation_key"], 100, required=True),
        "analyses": [_analysis(item) for item in _tuple(p["analyses"], 1, 32)],
        "assessments": [_assessment(item) for item in _tuple(p["assessments"], 1, 32)],
    }


def _check_projection(body, payload_digest, page_key):
    _require(type(body) is bytes and 1 <= len(body) <= MAX_BYTES, "invalid_value")
    _require(compare_digest(sha256(body).hexdigest(), _digest(payload_digest)), "binding")
    projection = _parse(body)
    if page_key is not None:
        _require(projection.keys() == {"page_key", "elements"})
        _require(_digest(projection["page_key"]) == _digest(page_key), "binding")
        for element in _array(projection["elements"], 1, 25):
            _require(_object(element).keys() == {"kind", "node_id", "name", "source_id", "target_id"})
            _text(element["kind"], 1, 256)
            if element["node_id"] is None:
                _require(element["name"] is None)
                _text(element["source_id"], 1, 256)
                _text(element["target_id"], 1, 256)
            else:
                _text(element["node_id"], 1, 256)
                _text(element["name"], 0, MAX_TEXT_BYTES)
                _require(element["source_id"] is None and element["target_id"] is None)


def decode_response(operation, p, *, run_id, task_id, lease_epoch, scope_ref, snapshot_digest):
    binding = dict(run_id=_uuid(p["run_id"]), task_id=_uuid(p["task_id"]),
                   lease_epoch=_integer(p["lease_epoch"], 0, 2**63-1))
    _require(
        binding["run_id"] == _uuid(run_id) and binding["task_id"] == _uuid(task_id)
        and binding["lease_epoch"] == _integer(lease_epoch, 0, 2**63-1),
        "binding",
    )
    if operation == "pfmea_impact_confirm":
        _require(p.keys() == binding.keys() | {"confirmation_id", "coverage_id"})
        coverage = p["coverage_id"]
        return models.PfmeaImpactConfirmation(_uuid(p["confirmation_id"]),
            None if coverage is None else _uuid(coverage), **binding)
    if operation == "pfmea_impact_result":
        _require(p.keys() == binding.keys() | {"result_id"})
        return models.PfmeaImpactResultRef(_uuid(p["result_id"]), **binding)

    _require(p.keys() == _RELEASE_KEYS)
    actual_snapshot = _digest(p["snapshot_digest"])
    if snapshot_digest is not None:
        _require(actual_snapshot == _digest(snapshot_digest), "binding")
    if operation == "pfmea_impact_page":
        _require(snapshot_digest is not None, "binding")
        _require(_handle(p["scope_ref"]) == _handle(scope_ref), "binding")
        page_key, token = _digest(p["page_key"]), _digest(p["confirmation_token"])
    else:
        _require(p["scope_ref"] is None and p["page_key"] is None and p["confirmation_token"] is None)
        page_key = token = None
    cursor = _cursor(p["next_cursor"])
    _require(operation != "pfmea_impact_material" or cursor is None)
    encoded = _text(p["projection_bytes"], 1, _MAX_B64_LENGTH)
    try:
        decoded = base64.b64decode(encoded, validate=True)
    except (Base64Error, ValueError):
        raise _Invalid("schema") from None
    _require(base64.b64encode(decoded).decode("ascii") == encoded)
    digest = _digest(p["payload_digest"])
    _check_projection(decoded, digest, page_key)
    return models.PfmeaImpactRelease(
        receipt_id=_uuid(p["receipt_id"]), projection_bytes=decoded, payload_digest=digest,
        snapshot_digest=actual_snapshot, scope_ref=p["scope_ref"], page_key=page_key,
        confirmation_token=token, next_cursor=cursor, **binding,
    )


def expected_snapshot(operation, digest):
    try:
        return _digest(digest)
    except _Invalid:
        pass
    raise ValidationError(operation, kind="invalid_value") from None


def confirmation_parameters(page, claim):
    try:
        _require(type(page) is models.PfmeaImpactRelease, "invalid_type")
        _require(page.run_id == claim.run_id and page.task_id == claim.task_id
                 and page.lease_epoch == claim.lease_epoch, "binding")
        _integer(page.lease_epoch, 0, 2**63-1)
        _digest(page.snapshot_digest)
        _handle(page.scope_ref)
        key = _digest(page.page_key)
        _check_projection(page.projection_bytes, page.payload_digest, key)
        return {
            "release_id": _uuid(page.receipt_id), "page_key": key,
            "payload_digest": page.payload_digest, "token": _digest(page.confirmation_token),
        }
    except (_Invalid, UnicodeDecodeError, ValueError, TypeError, RecursionError, KeyError):
        pass
    raise ValidationError("pfmea_impact_confirm", kind="invalid_request") from None
