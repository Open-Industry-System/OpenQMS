import hashlib
import json
import os
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "check-release-tree.py"
SECRET_PATH = "must-not-leak-secret-name.txt"


def _run(*args: str, input_bytes: bytes | None = None):
    return subprocess.run(
        ["python3", str(SCRIPT), *args],
        input=input_bytes,
        capture_output=True,
        timeout=15,
        check=False,
    )


def _manifest_line(path: str, payload: bytes, mode: str = "100644") -> str:
    return f"{mode} {hashlib.sha256(payload).hexdigest()}  {path}\n"


def _write_deployable(path: Path, payload: bytes) -> None:
    """Model a Git 100644 file regardless of the acceptance runner's umask."""
    path.write_bytes(payload)
    path.chmod(0o644)


def _write_manifest(root: Path, paths: list[str]) -> Path:
    result = _run(
        "create",
        "--root",
        str(root),
        input_bytes=b"\0".join(path.encode() for path in paths) + b"\0",
    )
    assert result.returncode == 0, result.stderr.decode()
    manifest = root / ".release-manifest"
    manifest.write_bytes(result.stdout)
    return manifest


def test_script_creates_sorted_deterministic_manifest_and_verifies_tree(tmp_path):
    (tmp_path / "z.txt").write_bytes(b"last")
    (tmp_path / "z.txt").chmod(0o755)
    nested = tmp_path / "dir"
    nested.mkdir()
    _write_deployable(nested / "a.txt", b"first")

    first = _run(
        "create",
        "--root",
        str(tmp_path),
        input_bytes=b"z.txt\0dir/a.txt\0",
    )
    second = _run(
        "create",
        "--root",
        str(tmp_path),
        input_bytes=b"dir/a.txt\0z.txt\0",
    )

    assert first.returncode == 0
    assert first.stderr == b""
    assert first.stdout == second.stdout == (
        _manifest_line("dir/a.txt", b"first")
        + _manifest_line("z.txt", b"last", "100755")
    ).encode()
    manifest = tmp_path / ".release-manifest"
    manifest.write_bytes(first.stdout)

    verification = _run(
        "verify", "--root", str(tmp_path), "--manifest", str(manifest)
    )

    assert verification.returncode == 0
    assert verification.stdout == b"release tree verification OK\n"
    assert verification.stderr == b""


@pytest.mark.parametrize(
    ("mutation", "expected_error"),
    [
        ("modified", "error: release tree content mismatch\n"),
        ("missing", "error: release tree path set mismatch\n"),
        ("extra", "error: release tree path set mismatch\n"),
    ],
)
def test_verify_rejects_modified_missing_and_extra_files_with_fixed_errors(
    tmp_path, mutation, expected_error
):
    tracked = tmp_path / "tracked.txt"
    _write_deployable(tracked, b"original")
    manifest = _write_manifest(tmp_path, ["tracked.txt"])

    if mutation == "modified":
        tracked.write_bytes(b"changed")
    elif mutation == "missing":
        tracked.unlink()
    else:
        (tmp_path / SECRET_PATH).write_bytes(b"unexpected")

    result = _run(
        "verify", "--root", str(tmp_path), "--manifest", str(manifest)
    )

    assert result.returncode != 0
    assert result.stdout == b""
    assert result.stderr.decode() == expected_error
    assert SECRET_PATH not in result.stderr.decode()


def test_verify_excludes_only_persistent_runtime_state(tmp_path):
    _write_deployable(tmp_path / "tracked.txt", b"tracked")
    manifest = _write_manifest(tmp_path, ["tracked.txt"])
    (tmp_path / ".env.production").write_bytes(b"SECRET=value\n")
    (tmp_path / ".release-sha").write_text("a" * 40 + "\n")
    backups = tmp_path / "backups" / "postgres"
    backups.mkdir(parents=True)
    (backups / "daily.dump").write_bytes(b"dump")

    result = _run(
        "verify", "--root", str(tmp_path), "--manifest", str(manifest)
    )

    assert result.returncode == 0
    assert result.stdout == b"release tree verification OK\n"
    assert b"SECRET=value" not in result.stdout + result.stderr


@pytest.mark.parametrize(
    ("manifest_mode", "remote_mode"),
    [(0o755, 0o644), (0o644, 0o755)],
    ids=("executable-removed", "executable-added"),
)
def test_verify_rejects_executable_mode_drift(
    tmp_path, manifest_mode, remote_mode
):
    tracked = tmp_path / "tracked.sh"
    tracked.write_bytes(b"#!/bin/sh\nexit 0\n")
    tracked.chmod(manifest_mode)
    manifest = _write_manifest(tmp_path, ["tracked.sh"])
    tracked.chmod(remote_mode)

    result = _run(
        "verify", "--root", str(tmp_path), "--manifest", str(manifest)
    )

    assert result.returncode != 0
    assert result.stdout == b""
    assert result.stderr == b"error: release tree mode mismatch\n"


@pytest.mark.parametrize(
    "unsafe_path",
    [b"../outside", b"/absolute", b"line\nbreak", b"carriage\rreturn", b"dir/../file"],
)
def test_create_rejects_unsafe_or_newline_paths(tmp_path, unsafe_path):
    result = _run(
        "create",
        "--root",
        str(tmp_path),
        input_bytes=unsafe_path + b"\0",
    )

    assert result.returncode != 0
    assert result.stdout == b""
    assert result.stderr == b"error: invalid release path\n"


def test_create_rejects_duplicate_nonregular_and_unsupported_mode_paths(tmp_path):
    directory = tmp_path / "directory"
    directory.mkdir()
    unsupported = tmp_path / "private.txt"
    unsupported.write_bytes(b"private")
    unsupported.chmod(0o600)

    duplicate = _run(
        "create",
        "--root",
        str(tmp_path),
        input_bytes=b"missing\0missing\0",
    )
    nonregular = _run(
        "create",
        "--root",
        str(tmp_path),
        input_bytes=b"directory\0",
    )
    unsupported_mode = _run(
        "create",
        "--root",
        str(tmp_path),
        input_bytes=b"private.txt\0",
    )

    assert duplicate.returncode != 0
    assert duplicate.stderr == b"error: duplicate release path\n"
    assert nonregular.returncode != 0
    assert nonregular.stderr == b"error: release path is not a regular file\n"
    assert unsupported_mode.returncode != 0
    assert unsupported_mode.stderr == b"error: release path has unsupported mode\n"


def test_verify_rejects_malformed_or_untrusted_manifest(tmp_path):
    manifest = tmp_path / ".release-manifest"
    manifest.write_text(json.dumps({"path": SECRET_PATH}))

    result = _run(
        "verify", "--root", str(tmp_path), "--manifest", str(manifest)
    )

    assert result.returncode != 0
    assert result.stdout == b""
    assert result.stderr == b"error: invalid release manifest\n"
    assert SECRET_PATH.encode() not in result.stderr


@pytest.mark.parametrize(
    ("reserved_name", "wrong_kind"),
    [
        (".env.production", "directory"),
        (".env.production", "symlink"),
        (".env.production", "fifo"),
        (".release-sha", "directory"),
        (".release-sha", "symlink"),
        (".release-manifest", "directory"),
        (".release-manifest", "symlink"),
        ("backups", "file"),
        ("backups", "symlink"),
    ],
)
def test_verify_rejects_wrong_type_reserved_runtime_paths(
    tmp_path, reserved_name, wrong_kind
):
    tracked = tmp_path / "tracked.txt"
    _write_deployable(tracked, b"tracked")
    created = _run(
        "create",
        "--root",
        str(tmp_path),
        input_bytes=b"tracked.txt\0",
    )
    assert created.returncode == 0
    manifest = tmp_path.parent / f"{tmp_path.name}-manifest"
    manifest.write_bytes(created.stdout)
    reserved = tmp_path / reserved_name
    target = tmp_path.parent / f"{tmp_path.name}-target"

    if wrong_kind == "directory":
        reserved.mkdir()
    elif wrong_kind == "file":
        reserved.write_bytes(b"wrong type")
    elif wrong_kind == "fifo":
        os.mkfifo(reserved, mode=0o600)
    else:
        target.write_bytes(b"symlink target")
        reserved.symlink_to(target)

    result = _run(
        "verify", "--root", str(tmp_path), "--manifest", str(manifest)
    )

    assert result.returncode != 0
    assert result.stdout == b""
    assert result.stderr == b"error: release tree path set mismatch\n"
    assert reserved_name.encode() not in result.stderr


def test_verify_rejects_symlink_as_extra_deployable_path(tmp_path):
    _write_deployable(tmp_path / "tracked.txt", b"tracked")
    manifest = _write_manifest(tmp_path, ["tracked.txt"])
    outside = tmp_path.parent / "outside.txt"
    outside.write_bytes(b"outside")
    (tmp_path / "unexpected-link").symlink_to(outside)

    result = _run(
        "verify", "--root", str(tmp_path), "--manifest", str(manifest)
    )

    assert result.returncode != 0
    assert result.stderr == b"error: release tree path set mismatch\n"
