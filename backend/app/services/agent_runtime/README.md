# Agent runtime services

## Controlled attachments

`attachment_storage.py` is a private filesystem primitive for scan-gated task attachments. It accepts only validated, server-generated namespaces and attachment UUIDs; it never accepts or returns filenames, storage keys, or paths. The storage root and namespace directories are `0700`, staging files are `0600`, symlinks are rejected, and `promote`/`open_clean` revalidate the caller-provided SHA-256 and size.

`clamav_scan.py` is an internal ClamAV `zINSTREAM` wire client. It sends `zVERSIONCOMMANDS\0`, then `zINSTREAM\0` and big-endian chunk frames ending in a zero-length frame. It uses one bounded 60-second-or-less exchange, accepts only a strict single `OK`, `FOUND`, or `ERROR` result, and collapses connection, timeout, malformed, and daemon-error cases to `unavailable` without exposing daemon failure text.

These primitives are not routes and do not enable attachment upload, plugin/model delivery, or lifecycle behavior.
