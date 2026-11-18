"""Pinned, stdlib-only worker for the managed PFMEA impact runtime."""
import base64
import http.client
import json
import re
import sys
import time
from datetime import UTC, datetime
from hashlib import sha256
from hmac import compare_digest
from urllib.parse import urlsplit
from uuid import UUID

PREFIX = "/api/agent/runtime/pfmea-impact"
ROUTES = {
    "material": "GET",
    "infer": "POST",
    "search": "POST",
    "page": "POST",
    "confirm": "POST",
    "result": "POST",
}
BINDING_FIELDS = {"run_id", "task_id", "lease_epoch"}
LAUNCH_FIELDS = BINDING_FIELDS | {
    "protocol", "profile", "api_origin", "tenant_slug", "token", "deployment_id",
    "lease_expires_at", "accepted_message_seq", "has_resume_checkpoint",
}
RELEASE_FIELDS = {
    "receipt_id", "projection_bytes", "payload_digest", "snapshot_digest",
    "scope_ref", "page_key", "confirmation_token", "next_cursor",
}
MAX_PROJECTION = 256 * 1024
MAX_JSON = 512 * 1024


def require(condition):
    if not condition:
        raise ValueError("Invalid runtime data")


def exact(value, fields):
    require(type(value) is dict and value.keys() == fields)
    return value


def unique_object(pairs):
    value = dict(pairs)
    require(len(value) == len(pairs))
    return value


def reject_constant(_):
    raise ValueError("Invalid JSON constant")


def parse(raw):
    require(0 < len(raw) <= MAX_JSON)
    value = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_object, parse_constant=reject_constant)
    require(type(value) is dict)
    return value


def text(value, maximum, *, minimum=1):
    require(type(value) is str and minimum <= len(value.encode("utf-8")) <= maximum and "\x00" not in value)
    return value


def match(pattern, value):
    require(type(value) is str and re.fullmatch(pattern, value) is not None)
    return value


def cursor(value):
    return None if value is None else match(r"[!-~]{1,4096}", value)


def digest(value):
    return match(r"[0-9a-f]{64}", value)


def identifier(value):
    require(type(value) is str and str(UUID(value)) == value)
    return value


def sequence_number(value):
    require(type(value) is int and 0 <= value <= 2**63 - 1)
    return value


class Runtime:
    def __init__(self, config):
        exact(config, LAUNCH_FIELDS)
        require((config["protocol"], config["profile"]) == ("r7.pfmea.launch.v1", "model_pfmea_impact_v1"))
        sequence_number(config["accepted_message_seq"])
        require(type(config["has_resume_checkpoint"]) is bool)
        expiry = datetime.fromisoformat(text(config["lease_expires_at"], 100))
        require(expiry.tzinfo is not None)
        remaining = (expiry - datetime.now(UTC)).total_seconds()
        require(remaining > 0)
        self.deadline = time.monotonic() + min(120, remaining)
        origin = urlsplit(match(r"http://127\.0\.0\.1:[0-9]{1,5}", config["api_origin"]))
        require(origin.port and 0 < origin.port <= 65535)
        self.host, self.port = origin.hostname, origin.port
        self.run_id = identifier(config["run_id"])
        self.task_id = identifier(config["task_id"])
        self.lease_epoch = sequence_number(config["lease_epoch"])
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": "Bearer " + match(r"[A-Za-z0-9._-]{1,8192}", config["token"]),
            "X-Tenant-ID": match(r"[a-zA-Z0-9._-]{1,100}", config["tenant_slug"]),
            "X-OpenQMS-Task": self.task_id,
            "X-OpenQMS-Run": self.run_id,
            "X-OpenQMS-Lease": str(self.lease_epoch),
            "X-OpenQMS-Deployment": identifier(config["deployment_id"]),
        }

    def request(self, route, data=None):
        remaining = self.deadline - time.monotonic()
        require(remaining > 0)
        body = None if data is None else json.dumps(data, ensure_ascii=False, allow_nan=False).encode("utf-8")
        require(body is None or len(body) <= MAX_JSON)
        connection = http.client.HTTPConnection(self.host, self.port, timeout=min(30, remaining))
        try:
            connection.request(ROUTES[route], f"{PREFIX}/{route}", body=body, headers=self.headers)
            with connection.getresponse() as response:
                require(response.status == 200 and response.headers.get_content_type() == "application/json")
                value = parse(response.read(MAX_JSON + 1))
        finally:
            connection.close()
        require(
            identifier(value["run_id"]) == self.run_id and identifier(value["task_id"]) == self.task_id
            and sequence_number(value["lease_epoch"]) == self.lease_epoch
        )
        return value

    def release(self, route, data=None, *, snapshot=None, scope=None):
        value = exact(self.request(route, data), BINDING_FIELDS | RELEASE_FIELDS)
        receipt = identifier(value["receipt_id"])
        expected_digest = digest(value["payload_digest"])
        snapshot_digest = digest(value["snapshot_digest"])
        require(snapshot is None or snapshot_digest == snapshot)
        require(value["scope_ref"] == scope)
        next_cursor = cursor(value["next_cursor"])
        require(route != "material" or next_cursor is None)
        encoded = text(value["projection_bytes"], ((MAX_PROJECTION + 2) // 3) * 4)
        raw = base64.b64decode(encoded, validate=True)
        require(0 < len(raw) <= MAX_PROJECTION and base64.b64encode(raw).decode("ascii") == encoded)
        require(compare_digest(sha256(raw).hexdigest(), expected_digest))
        projection = parse(raw)
        if projection.keys() == {"gap"}:
            require(route in {"page", "search"} and projection["gap"] in ("scope_incomplete", "budget_exhausted"))
            require(value["page_key"] is None and value["confirmation_token"] is None and next_cursor is None)
            return snapshot_digest
        if route == "page":
            key = digest(value["page_key"])
            check_page(projection, key)
            ack = exact(self.request("confirm", {
                "release_id": receipt, "page_key": key, "payload_digest": expected_digest,
                "token": digest(value["confirmation_token"]),
            }), BINDING_FIELDS | {"confirmation_id", "coverage_id"})
            identifier(ack["confirmation_id"])
            if ack["coverage_id"] is not None:
                identifier(ack["coverage_id"])
        else:
            require(value["page_key"] is None and value["confirmation_token"] is None)
        return snapshot_digest


def check_page(projection, key):
    exact(projection, {"page_key", "elements"})
    require(digest(projection["page_key"]) == key)
    elements = projection["elements"]
    require(type(elements) is list and 1 <= len(elements) <= 25)
    for element in elements:
        exact(element, {"kind", "node_id", "name", "source_id", "target_id"})
        text(element["kind"], 256)
        if element["node_id"] is None:
            require(element["name"] is None)
            text(element["source_id"], 256)
            text(element["target_id"], 256)
        else:
            text(element["node_id"], 256)
            text(element["name"], 16 * 1024, minimum=0)
            require(element["source_id"] is None and element["target_id"] is None)


def check_candidate(analyses, assessments):
    require(type(analyses) is list and 1 <= len(analyses) <= 32)
    require(type(assessments) is list and 1 <= len(assessments) <= 32)
    for analysis in analyses:
        exact(analysis, {"analysis_ref", "reason", "fact_refs", "inference"})
    for assessment in assessments:
        exact(assessment, {
            "measure_id", "formal_revision", "analysis_ref", "conclusion", "evidence_refs",
            "coverage_refs", "exclusion_refs", "missing_information", "node_adjustments",
        })
        require(type(assessment["node_adjustments"]) is list and len(assessment["node_adjustments"]) <= 256)
        for adjustment in assessment["node_adjustments"]:
            exact(adjustment, {"target_ref", "proposal"})


def main():
    runtime = Runtime(parse(sys.stdin.buffer.read(16 * 1024 + 1)))
    snapshot = runtime.release("material")
    # Permit sixteen discovery or page actions and one final completion decision.
    for turn in range(17):
        reply = exact(runtime.request("infer", {}), BINDING_FIELDS | {"action"})
        action = reply["action"]
        require(type(action) is dict)
        kind = action["kind"]
        if kind == "complete":
            exact(action, {"kind", "analyses", "assessments"})
            analyses, assessments = action["analyses"], action["assessments"]
            check_candidate(analyses, assessments)
            result = exact(runtime.request("result", {
                "operation_key": f"pfmea-impact:{runtime.run_id}:{runtime.lease_epoch}",
                "analyses": analyses, "assessments": assessments,
            }), BINDING_FIELDS | {"result_id"})
            identifier(result["result_id"])
            return
        require(turn < 16)
        if kind == "search":
            exact(action, {"kind", "term", "cursor"})
            term = text(action["term"], 120)
            require(term.strip())
            runtime.release("search", {"term": term, "cursor": cursor(action["cursor"])}, snapshot=snapshot)
        elif kind == "page":
            exact(action, {"kind", "scope_ref", "cursor"})
            scope = match(r"[!-~]{1,4096}", action["scope_ref"])
            runtime.release("page", {"scope_ref": scope, "cursor": cursor(action["cursor"])},
                            snapshot=snapshot, scope=scope)
        else:
            raise ValueError("Runtime did not offer a supported action")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # Suppress original source, model output and launch credentials.
        sys.exit(1)
