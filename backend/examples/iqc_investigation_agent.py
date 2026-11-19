"""Pinned stdlib-only IQC worker; its only socket is the exact local platform."""

import http.client
import json
import re
import sys
import time
from datetime import datetime
from urllib.parse import urlsplit
from uuid import UUID

PREFIX = "/api/agent/runtime/iqc-investigation"
MAX_JSON = 1024 * 1024
MAX_ACTION = 32 * 1024
ROUTES = {
    "context": "GET", "items": "POST", "reinspections": "POST", "associations": "POST",
    "history": "POST", "material": "POST", "supplier": "POST", "infer": "POST", "result": "POST",
}
PROJECTIONS = {
    "context": "iqc.inspection.context.v1", "items": "iqc.inspection.items.v1",
    "reinspections": "iqc.inspection.reinspection_chain.v1",
    "associations": "iqc.investigation.associations.v1", "history": "iqc.inspection.related_history.v1",
    "material": "iqc.material.current_summary.v1", "supplier": "supplier.current_summary.v1",
}
BINDING_FIELDS = {"task_id", "run_id", "lease_epoch"}


class ResultRejected(ValueError):
    pass


def require(condition):
    if not condition:
        raise ValueError("Invalid controlled IQC protocol")


def exact(value, keys):
    require(type(value) is dict and value.keys() == keys)
    return value


def text(value, maximum):
    require(type(value) is str and 0 < len(value.encode("utf-8")) <= maximum and "\0" not in value)
    return value


def match(pattern, value):
    require(type(value) is str and re.fullmatch(pattern, value) is not None)
    return value


def identifier(value):
    require(type(value) is str and str(UUID(value)) == value)
    return value


def integer(value):
    require(type(value) is int and 0 <= value <= 2147483647)
    return value


def _unique(pairs):
    value = {}
    for key, item in pairs:
        require(key not in value)
        value[key] = item
    return value


def _constant(_):
    raise ValueError("Invalid JSON constant")


def parse(raw):
    require(type(raw) is bytes and 0 < len(raw) <= MAX_JSON)
    result = json.loads(raw, object_pairs_hook=_unique, parse_constant=_constant)
    require(type(result) is dict)
    return result


def cursor(value):
    return None if value is None else match(r"[A-Za-z0-9_=.\-]{1,4096}", value)


class Runtime:
    def __init__(self, config):
        exact(config, {"protocol", "profile", "api_origin", "token", "tenant_slug", "task_id",
                       "run_id", "deployment_id", "lease_epoch", "lease_expires_at"})
        require(config["protocol"] == "r7.iqc.launch.v1" and config["profile"] == "model_iqc_investigation_v1")
        origin = urlsplit(config["api_origin"])
        require(origin.scheme == "http" and origin.hostname == "127.0.0.1"
                and origin.path in ("", "/") and not origin.query and not origin.fragment
                and origin.username is None and origin.password is None
                and origin.port is not None and 1 <= origin.port <= 65535)
        expiry = datetime.fromisoformat(config["lease_expires_at"])
        require(expiry.tzinfo is not None and expiry.timestamp() > time.time())
        self.deadline = time.monotonic() + min(110, expiry.timestamp() - time.time())
        self.host, self.port = origin.hostname, origin.port
        self.task_id, self.run_id = identifier(config["task_id"]), identifier(config["run_id"])
        self.epoch = integer(config["lease_epoch"])
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": "Bearer " + match(r"[A-Za-z0-9._-]{1,8192}", config["token"]),
            "X-Tenant-ID": match(r"[a-zA-Z0-9._-]{1,100}", config["tenant_slug"]),
            "X-OpenQMS-Task": self.task_id, "X-OpenQMS-Run": self.run_id,
            "X-OpenQMS-Lease": str(self.epoch), "X-OpenQMS-Deployment": identifier(config["deployment_id"]),
        }

    def request(self, route, data=None):
        require(route in ROUTES)
        remaining = self.deadline - time.monotonic()
        require(remaining > 0)
        body = None if data is None else json.dumps(data, ensure_ascii=False, allow_nan=False).encode("utf-8")
        require(body is None or len(body) <= MAX_ACTION)
        connection = http.client.HTTPConnection(self.host, self.port, timeout=min(30, remaining))
        try:
            connection.request(ROUTES[route], f"{PREFIX}/{route}", body=body, headers=self.headers)
            with connection.getresponse() as response:
                if route == "result" and response.status == 409:
                    raise ResultRejected()
                require(response.status == 200 and response.headers.get_content_type() == "application/json")
                result = parse(response.read(MAX_JSON + 1))
        finally:
            connection.close()
        require(identifier(result["task_id"]) == self.task_id
                and identifier(result["run_id"]) == self.run_id and integer(result["lease_epoch"]) == self.epoch)
        return result

    def read(self, route, data=None):
        result = self.request(route, data)
        require(type(result.get("available")) is bool and result.get("projection") == PROJECTIONS[route])
        if not result["available"]:
            exact(result, BINDING_FIELDS | {"available", "projection", "reason"})
            require(result["reason"] in {"unavailable", "budget_exhausted"})
            return
        exact(result, BINDING_FIELDS | {"available", "receipt_id", "projection", "version", "data", "params", "continuation"})
        identifier(result["receipt_id"])
        match(r"[0-9a-f]{64}", result["version"])
        require(type(result["data"]) is dict and type(result["params"]) is dict)
        cursor(result["continuation"])


def check_card(card):
    exact(card, {"action", "evidence_refs", "missing", "next_steps", "include_d2"})
    require(card["action"] in {"check_existing", "supplement_existing", "consider_new"})
    require(type(card["evidence_refs"]) is list and 1 <= len(card["evidence_refs"]) <= 64)
    for reference in card["evidence_refs"]:
        identifier(reference)
    require(type(card["missing"]) is list and len(card["missing"]) <= 20)
    require(type(card["next_steps"]) is list and len(card["next_steps"]) <= 20)
    # Exact enum membership is independently checked by the platform result schema.
    require(all(type(code) is str and re.fullmatch(r"[a-z_]{1,80}", code) for code in card["missing"]))
    require(all(type(code) is str and re.fullmatch(r"[a-z_]{1,80}", code) for code in card["next_steps"]))
    require(type(card["include_d2"]) is bool)


def main():
    runtime = Runtime(parse(sys.stdin.buffer.read(16 * 1024 + 1)))
    runtime.read("context")
    runtime.read("reinspections", {})
    # The model chooses any further authorized read; it never chooses a host,
    # write command, arbitrary instruction, model deployment or runtime identity.
    for turn in range(17):
        response = exact(runtime.request("infer", {}), BINDING_FIELDS | {"action"})
        action = response["action"]
        require(type(action) is dict)
        kind = action.get("kind")
        if kind == "complete":
            exact(action, {"kind", "card"})
            check_card(action["card"])
            submission = {
                "operation_key": f"iqc-investigation:{runtime.run_id}:{runtime.epoch}", "card": action["card"],
            }
            try:
                reply = runtime.request("result", submission)
            except ResultRejected:
                require(submission["card"]["action"] != "check_existing")
                submission["card"]["action"] = "check_existing"
                reply = runtime.request("result", submission)
            result = exact(reply, BINDING_FIELDS | {"result_id"})
            identifier(result["result_id"])
            return
        require(turn < 16 and kind == "read")
        exact(action, {"kind", "tool", "inspection_id", "item_id", "cursor"})
        route = action["tool"]
        require(route in PROJECTIONS and route != "context")
        if route == "items":
            params = dict(inspection_id=None if action["inspection_id"] is None else identifier(action["inspection_id"]),
                item_id=None if action["item_id"] is None else identifier(action["item_id"]), cursor=cursor(action["cursor"]))
        else:
            require(action["inspection_id"] is None and action["item_id"] is None)
            params = {"cursor": cursor(action["cursor"])} if route == "history" else {}
            require(route == "history" or action["cursor"] is None)
        runtime.read(route, params)
    raise ValueError("IQC model budget exhausted")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # Source/model bodies and launch credentials never become process logs.
        sys.exit(1)
