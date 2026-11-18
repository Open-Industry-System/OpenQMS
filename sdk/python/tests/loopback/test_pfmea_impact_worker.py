"""Exercise the artifact as a standalone process against the R7 loopback wire."""
import base64
import json
import subprocess
import sys
import threading
import unittest
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from socketserver import TCPServer
from uuid import UUID

ARTIFACT = Path(__file__).resolve().parents[4] / "backend/examples/pfmea_impact_agent.py"
TASK, RUN, DEPLOYMENT, RECEIPT, CONFIRMATION, COVERAGE, RESULT = (
    str(UUID(int=value)) for value in range(1, 8)
)
BINDING = {"task_id": TASK, "run_id": RUN, "lease_epoch": 2}
PREFIX = "/api/agent/runtime/pfmea-impact"
SCOPE = "opaque-scope"
KEY = "a" * 64
SNAPSHOT = "b" * 64
TOKEN = "c" * 64
ANALYSES = [
    {"analysis_ref": "A1", "reason": "工序相符", "fact_refs": ["source"], "inference": "核对夹具"}
]
ASSESSMENTS = [
    {
        "measure_id": RECEIPT, "formal_revision": CONFIRMATION, "analysis_ref": "A1",
        "conclusion": "insufficient_evidence", "evidence_refs": [], "coverage_refs": [],
        "exclusion_refs": [], "missing_information": ["夹具编号"], "node_adjustments": [],
    }
]


def launch(origin):
    return {
        **BINDING, "protocol": "r7.pfmea.launch.v1", "profile": "model_pfmea_impact_v1",
        "api_origin": origin, "tenant_slug": "r7", "token": "opaque.run-token",
        "lease_expires_at": (datetime.now(UTC) + timedelta(minutes=1)).isoformat(),
        "deployment_id": DEPLOYMENT, "accepted_message_seq": 0, "has_resume_checkpoint": False,
    }


def release(value, *, page=False, next_cursor=None):
    data = json.dumps(value).encode()
    return {
        **BINDING, "receipt_id": RECEIPT, "projection_bytes": base64.b64encode(data).decode(),
        "payload_digest": sha256(data).hexdigest(), "snapshot_digest": SNAPSHOT,
        "scope_ref": SCOPE if page else None, "page_key": KEY if page else None,
        "confirmation_token": TOKEN if page else None, "next_cursor": next_cursor,
    }


def answer(kind, **fields):
    return {**BINDING, "action": {"kind": kind, **fields}}


def page_body():
    return {
        "page_key": KEY, "elements": [
            {"kind": "process_step", "node_id": "step", "name": "夹具", "source_id": None, "target_id": None}
        ],
    }


def sequence(page):
    return [
        ("/material", release({"adopted": True})),
        ("/infer", answer("search", term="夹具", cursor=None)),
        ("/search", release({"matches": [SCOPE]}, next_cursor="search-next")),
        ("/infer", answer("search", term="夹具", cursor="search-next")),
        ("/search", release({"matches": [SCOPE]})),
        ("/infer", answer("page", scope_ref=SCOPE, cursor=None)),
        ("/page", page),
        ("/confirm", {**BINDING, "confirmation_id": CONFIRMATION, "coverage_id": COVERAGE}),
        ("/infer", answer("complete", analyses=ANALYSES, assessments=ASSESSMENTS)),
        ("/result", {**BINDING, "result_id": RESULT}),
    ]


class NumericHTTPServer(ThreadingHTTPServer):
    def server_bind(self):
        TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address


class WorkerTest(unittest.TestCase):
    def run_worker(self, config):
        return subprocess.run(  # noqa: S603 - pinned example and current interpreter
            [sys.executable, "-I", str(ARTIFACT)], input=json.dumps(config),
            capture_output=True, text=True, timeout=8, check=False,
        )

    def visit(self, responses):
        received = []

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self._respond()

            def do_POST(self):
                self._respond()

            def log_message(self, *_):
                pass

            def _respond(self):
                raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                received.append((self.command, self.path, json.loads(raw) if raw else None, self.headers))
                index = len(received) - 1
                if index >= len(responses) or self.path != PREFIX + responses[index][0]:
                    self.send_error(400)
                    return
                reply = responses[index][1]
                if reply is None:
                    self.close_connection = True
                    return
                if isinstance(reply, int):
                    self.send_response(reply)
                    self.send_header("Location", f"{PREFIX}/infer")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                data = json.dumps(reply).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        with NumericHTTPServer(("127.0.0.1", 0), Handler) as server:
            thread = threading.Thread(target=server.serve_forever, args=(0.01,))
            thread.start()
            try:
                process = self.run_worker(launch(f"http://127.0.0.1:{server.server_port}"))
            finally:
                server.shutdown()
                thread.join()
        self.assertEqual((process.stdout, process.stderr), ("", ""))
        return process, received

    def test_worker_elects_model_actions_confirms_exact_page_and_publishes(self):
        page = release(page_body(), page=True)
        steps = sequence(page)
        process, requests = self.visit(steps)
        self.assertEqual(process.returncode, 0)
        self.assertEqual([path for _, path, _, _ in requests], [PREFIX + path for path, _ in steps])
        self.assertEqual([method for method, _, _, _ in requests], ["GET"] + ["POST"] * 9)
        self.assertEqual([body for _, path, body, _ in requests if path.endswith("/infer")], [{}] * 4)
        self.assertEqual(requests[2][2], {"term": "夹具", "cursor": None})
        self.assertEqual(requests[4][2], {"term": "夹具", "cursor": "search-next"})
        self.assertEqual(requests[6][2], {"scope_ref": SCOPE, "cursor": None})
        self.assertEqual(requests[7][2], {
            "release_id": RECEIPT, "page_key": KEY, "payload_digest": page["payload_digest"], "token": TOKEN,
        })
        submitted = requests[-1][2]
        self.assertEqual(submitted["analyses"], ANALYSES)
        self.assertEqual(submitted["assessments"], ASSESSMENTS)
        self.assertTrue(submitted["operation_key"])
        for _, _, _, headers in requests:
            self.assertEqual(headers["Authorization"], "Bearer opaque.run-token")
            self.assertEqual(headers["X-Tenant-ID"], "r7")
            self.assertEqual(headers["X-OpenQMS-Task"], TASK)
            self.assertEqual(headers["X-OpenQMS-Run"], RUN)
            self.assertEqual(headers["X-OpenQMS-Lease"], "2")
            self.assertEqual(headers["X-OpenQMS-Deployment"], DEPLOYMENT)

    def test_unverified_page_never_acks_or_submits(self):
        bad_page_key = {**page_body(), "page_key": "e" * 64}
        for page in (
            {**release(page_body(), page=True), "payload_digest": "e" * 64},
            {**release(page_body(), page=True), "scope_ref": "another-scope"},
            {**release(page_body(), page=True), "snapshot_digest": "e" * 64},
            {**release(page_body(), page=True), "lease_epoch": 3},
            release(bad_page_key, page=True),
        ):
            process, requests = self.visit(sequence(page))
            self.assertEqual(process.returncode, 1)
            self.assertEqual(len(requests), 7)

    def test_redirects_and_unrecognized_actions_never_call_another_endpoint(self):
        for reply in (307, answer("fail"), answer("https://example.com"), answer("search", term="x", cursor=None,
                                                                                 facts=["not a selector"])):
            process, requests = self.visit([("/material", release({})), ("/infer", reply)])
            self.assertEqual(process.returncode, 1)
            self.assertEqual(len(requests), 2)

    def test_ambiguous_publication_exits_without_retry(self):
        first = sequence(release(page_body(), page=True))
        first[-1] = ("/result", None)
        process, requests = self.visit(first)
        self.assertEqual(process.returncode, 1)
        self.assertEqual(len(requests), len(first))

    def test_unconfirmed_page_exits_without_advancing(self):
        steps = sequence(release(page_body(), page=True))
        steps[7] = ("/confirm", None)
        process, requests = self.visit(steps)
        self.assertEqual(process.returncode, 1)
        self.assertEqual(len(requests), 8)

    def test_model_cannot_force_more_than_sixteen_fmea_calls(self):
        steps = [("/material", release({}))]
        steps += [("/infer", answer("search", term="x", cursor=None)), ("/search", release({}))] * 16
        steps.append(("/infer", answer("search", term="x", cursor=None)))
        process, requests = self.visit(steps)
        self.assertEqual(process.returncode, 1)
        self.assertEqual(len(requests), len(steps))

    def test_unknown_nested_candidate_fields_are_never_submitted(self):
        steps = [
            ("/material", release({})),
            ("/infer", answer("complete", analyses=ANALYSES,
                              assessments=[{**ASSESSMENTS[0], "write_pfmea": True}])),
        ]
        process, requests = self.visit(steps)
        self.assertEqual(process.returncode, 1)
        self.assertEqual(len(requests), len(steps))

    def test_managed_launch_rejects_other_profiles_and_non_numeric_loopback(self):
        config = launch("http://127.0.0.1:1")
        for invalid in (
            {"profile": "model_d4_v1"},
            {"api_origin": "http://localhost:1"},
            {"api_origin": "http://127.0.0.1:1/path"},
            {"api_origin": "http://127.0.0.1@192.0.2.2:1"},
            {"token": "line\nbreak"},
        ):
            process = self.run_worker({**config, **invalid})
            self.assertEqual((process.returncode, process.stdout, process.stderr), (1, "", ""))


if __name__ == "__main__":
    unittest.main()
