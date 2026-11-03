# OpenQMS Agent SDK (0.1.0)

Independent Python >=3.11 src-layout package, distribution `openqms-agent-sdk`,
import `openqms_agent_sdk`. Runtime dependencies: none. No backend imports,
database access, implicit environment/profile credentials or model calls.

This foundation provides safe errors and immutable protocol DTOs. Client, codec
and transport are not implemented yet. Frozen/slotted DTOs and tuple annotations
are not runtime type validation: strict protocol decoding belongs to the codec.
Configuration only validates local resource budgets; origin validation belongs
to the future transport. Request budget is fixed at 1 MiB; response budget defaults
to 4 MiB (64 KiB–16 MiB); timeout defaults to 10 seconds (1–120).

## Authorization boundary

Examples and compatibility checks are **fixture-only** communication exercises.
This SDK is **not a newly admitted worker**, does not change the fixed worker,
hash, profile, catalog or official launch chain, and is not production admission.
Possession of credentials and successful HTTP communication do not grant worker
approval or additional authorization.

Business read-only does not mean no platform writes: message claim/ACK, receipts,
audit, events, restricted analysis results, checkpoints and terminal state are
platform records, not CAPA/FMEA business facts, approvals or adopted measures.
No new business writes, attachment/body access, model forwarding or execution of
message text is provided. Message and analysis text can still be sensitive.

## Safe errors

`SDKError(operation, *, kind, status=None, may_have_been_sent=False,
outcome_unknown=False)` is shared by all public error types. Only fixed internal
operation/kind names are retained; unrecognized values become `unknown`. HTTP
status is a strict integer in 100–599 or None. Raw exceptions, URLs, credentials,
headers and bodies must never be passed as messages or retained as original or
response objects. UnknownOutcome always sets outcome_unknown=True.

Internal diagnostic kinds (not server business codes): `unknown`,
`invalid_config`, `invalid_timeout`, `invalid_response_budget`, `invalid_url`,
`invalid_tenant`, `invalid_request`, `invalid_uuid`, `invalid_type`, `invalid_value`,
`request_too_large`, `timeout`, `dns`, `connection`, `tls`, `http_status`,
`redirect`, `invalid_response`, `invalid_json`, `invalid_utf8`, `duplicate_key`,
`schema`, `binding`, `unsupported_encoding`, `response_too_large`,
`outcome_unknown`, `client_closed`, `client_busy`, `transport`, `deadline`,
`dns_busy`, `connection_closed`.
Unknown-kind fallback is only safe diagnostics, never a basis for business flow.
Future wrappers must raise sanitized errors outside except blocks (or from None)
and must not echo underlying exception.args.

Build uses setuptools==79.0.1, with no additional wheel build requirement.
Wheel construction and isolated installation validation are later delivery gates.
