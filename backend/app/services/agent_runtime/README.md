# Agent runtime services

## Controlled attachments

`attachment_storage.py` is a private filesystem primitive for scan-gated task attachments. It accepts only validated, server-generated namespaces and attachment UUIDs; it never accepts or returns filenames, storage keys, or paths. The storage root and namespace directories are `0700`, staging files are `0600`, symlinks are rejected, and `promote`/`open_clean` revalidate the caller-provided SHA-256 and size.

`clamav_scan.py` is an internal ClamAV `zINSTREAM` wire client. It sends `zVERSIONCOMMANDS\0`, then `zINSTREAM\0` and big-endian chunk frames ending in a zero-length frame. It uses one bounded 60-second-or-less exchange, accepts only a strict single `OK`, `FOUND`, or `ERROR` result, and collapses connection, timeout, malformed, and daemon-error cases to `unavailable` without exposing daemon failure text.

`attachment_recovery.py` is platform/maintenance-only reconciliation. It serializes
with the attachment pipeline, finishes only durable `promoting`, expired
`scanning`, and `purging` metadata states in the exact current live namespace,
and preserves unknown or historical namespaces. Whole-generation removal requires
a durable exact platform disposal record (`test_rebuild` or future
`tenant_destroyed`); it never relies on upload-owner authority and cannot publish
an orphan file. When attachments are already enabled, startup validates and runs
one bounded reconciliation pass. A live pipeline lock defers that pass; other
validation/recovery failures leave attachments closed for that process. The fixed
`python -m app.cli.agent_task_attachments reconcile` command exposes the same
aggregate-only maintenance pass without accepting paths, tenants, or wildcards.

These primitives are not routes and do not enable attachment upload, plugin/model delivery, or lifecycle behavior.
