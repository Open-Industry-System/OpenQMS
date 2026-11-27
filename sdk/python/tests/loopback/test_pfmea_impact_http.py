"""Exercise R7's exact managed wire and explicit ACK on an owned loopback."""
import base64
import json
import socketserver
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
from uuid import UUID

import pytest

from openqms_agent_sdk import ManagedLaunch, ProtocolError, RunClient


RUN = UUID(int=1)
TASK = UUID(int=2)
RECEIPT = UUID(int=3)
DEPLOYMENT = UUID(int=4)
SNAPSHOT = "a" * 64
PAGE = "b" * 64
SCOPE = "server.scope"
TOKEN = "c" * 64
PREFIX = "/api/agent/runtime/pfmea-impact"


class _OwnedHTTPServer(HTTPServer):
    def server_bind(self):
        # HTTPServer.server_bind resolves a hostname even for numeric addresses.
        socketserver.TCPServer.server_bind(self)
        self.server_name = "127.0.0.1"
        self.server_port = self.server_address[1]


@pytest.mark.parametrize("corrupt", (False, True))
def test_managed_pfmea_page_verification_precedes_confirmation(corrupt):
    payload = json.dumps({"page_key": PAGE, "elements": [{
        "kind": "ProcessStep", "node_id": "step", "name": "OP40",
        "source_id": None, "target_id": None,
    }]}, separators=(",", ":")).encode()
    digest = sha256(payload).hexdigest()
    binding = {"run_id": str(RUN), "task_id": str(TASK), "lease_epoch": 3}
    envelope = binding | {
        "scope_ref": SCOPE, "snapshot_digest": SNAPSHOT, "receipt_id": str(RECEIPT),
        "projection_bytes": base64.b64encode(payload).decode(),
        "payload_digest": "e" * 64 if corrupt else digest, "page_key": PAGE,
        "confirmation_token": TOKEN, "next_cursor": "next.cursor",
    }
    responses = {PREFIX + "/page": envelope,
                 PREFIX + "/confirm": binding | {"confirmation_id": str(RECEIPT), "coverage_id": None}}
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append((self.path, self.headers, body))
            response = json.dumps(responses[self.path], separators=(",", ":")).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(response)))
            self.end_headers()
            self.wfile.write(response)

    with _OwnedHTTPServer(("127.0.0.1", 0), Handler) as server:
        thread = Thread(target=server.serve_forever, kwargs={"poll_interval": .05}, daemon=True)
        thread.start()
        try:
            launch = ManagedLaunch.from_dict(binding | {
                "protocol": "r7.pfmea.launch.v1", "profile": "model_pfmea_impact_v1",
                "api_origin": f"http://127.0.0.1:{server.server_port}", "tenant_slug": "test",
                "token": "credential", "deployment_id": str(DEPLOYMENT),
                "lease_expires_at": (datetime.now(timezone.utc) + timedelta(minutes=1)).isoformat(),
                "accepted_message_seq": 0, "has_resume_checkpoint": False,
            })
            with RunClient.from_launch(launch) as client:
                if corrupt:
                    with pytest.raises(ProtocolError):
                        client.pfmea_impact_page(scope_ref=SCOPE, snapshot_digest=SNAPSHOT, cursor="page.cursor")
                else:
                    page = client.pfmea_impact_page(scope_ref=SCOPE, snapshot_digest=SNAPSHOT, cursor="page.cursor")
                    assert page.next_cursor == "next.cursor"
                    assert page.projection_bytes == payload
                    assert len(requests) == 1
                    ack = client.pfmea_impact_confirm(page)
                    assert ack.confirmation_id == RECEIPT and ack.coverage_id is None
        finally:
            server.shutdown()
            thread.join(timeout=2)
            assert not thread.is_alive()

    assert [path for path, _, _ in requests] == (
        [PREFIX + "/page"] if corrupt else [PREFIX + "/page", PREFIX + "/confirm"]
    )
    for _, headers, _ in requests:
        assert headers["Authorization"] == "Bearer credential"
        assert headers["X-OpenQMS-Task"] == str(TASK)
        assert headers["X-OpenQMS-Run"] == str(RUN)
        assert headers["X-OpenQMS-Lease"] == "3"
        assert headers["X-OpenQMS-Deployment"] == str(DEPLOYMENT)
    assert requests[0][2] == {"scope_ref": SCOPE, "cursor": "page.cursor"}
    if not corrupt:
        assert requests[1][2] == {
            "release_id": str(RECEIPT), "page_key": PAGE, "token": TOKEN, "payload_digest": digest,
        }
