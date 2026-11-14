#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import os
import re
import stat
import sys
from pathlib import Path, PurePosixPath


_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_RUNTIME_FILES = {".env.production", ".release-manifest", ".release-sha"}


class ReleaseTreeError(Exception):
    pass


def _digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _validate_path(value: str) -> str:
    if not value or any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise ReleaseTreeError("invalid release path")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in ("", ".", "..") for part in path.parts):
        raise ReleaseTreeError("invalid release path")
    if path.as_posix() != value:
        raise ReleaseTreeError("invalid release path")
    return value


def _candidate(root: Path, relative_path: str) -> Path:
    candidate = root.joinpath(*PurePosixPath(relative_path).parts)
    try:
        mode = candidate.lstat().st_mode
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError):
        raise ReleaseTreeError("release path is not a regular file") from None
    if not stat.S_ISREG(mode) or resolved != candidate.absolute():
        raise ReleaseTreeError("release path is not a regular file")
    return candidate


def _git_mode(path: Path) -> str | None:
    mode = stat.S_IMODE(path.lstat().st_mode)
    if mode == 0o644:
        return "100644"
    if mode == 0o755:
        return "100755"
    return None


def _read_null_paths() -> list[str]:
    payload = sys.stdin.buffer.read()
    if not payload or not payload.endswith(b"\0"):
        raise ReleaseTreeError("invalid release path")
    encoded_paths = payload[:-1].split(b"\0")
    try:
        paths = [_validate_path(item.decode("utf-8")) for item in encoded_paths]
    except UnicodeDecodeError:
        raise ReleaseTreeError("invalid release path") from None
    if len(paths) != len(set(paths)):
        raise ReleaseTreeError("duplicate release path")
    return sorted(paths)


def create_manifest(root_argument: str) -> None:
    try:
        root = Path(root_argument).resolve(strict=True)
    except OSError:
        raise ReleaseTreeError("release root is not readable") from None
    if not root.is_dir():
        raise ReleaseTreeError("release root is not readable")

    paths = _read_null_paths()
    lines = []
    for relative_path in paths:
        candidate = _candidate(root, relative_path)
        git_mode = _git_mode(candidate)
        if git_mode is None:
            raise ReleaseTreeError("release path has unsupported mode")
        try:
            digest = _digest(candidate)
        except OSError:
            raise ReleaseTreeError("release path is not readable") from None
        lines.append(f"{git_mode} {digest}  {relative_path}\n")
    sys.stdout.write("".join(lines))


def _read_manifest(path: Path) -> list[tuple[str, str, str]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        raise ReleaseTreeError("invalid release manifest") from None
    if not lines:
        raise ReleaseTreeError("invalid release manifest")

    entries: list[tuple[str, str, str]] = []
    try:
        for line in lines:
            git_mode, remainder = line.split(" ", 1)
            digest, relative_path = remainder.split("  ", 1)
            if git_mode not in ("100644", "100755"):
                raise ReleaseTreeError("invalid release manifest")
            if _HASH_RE.fullmatch(digest) is None:
                raise ReleaseTreeError("invalid release manifest")
            entries.append((git_mode, digest, _validate_path(relative_path)))
    except (ValueError, ReleaseTreeError):
        raise ReleaseTreeError("invalid release manifest") from None

    paths = [relative_path for _, _, relative_path in entries]
    if paths != sorted(paths) or len(paths) != len(set(paths)):
        raise ReleaseTreeError("invalid release manifest")
    return entries


def _validate_runtime_state(root: Path) -> None:
    for name in _RUNTIME_FILES:
        candidate = root / name
        try:
            mode = candidate.lstat().st_mode
        except FileNotFoundError:
            continue
        except OSError:
            raise ReleaseTreeError("release tree path set mismatch") from None
        if not stat.S_ISREG(mode):
            raise ReleaseTreeError("release tree path set mismatch")

    backups = root / "backups"
    try:
        backups_mode = backups.lstat().st_mode
    except FileNotFoundError:
        return
    except OSError:
        raise ReleaseTreeError("release tree path set mismatch") from None
    if not stat.S_ISDIR(backups_mode):
        raise ReleaseTreeError("release tree path set mismatch")


def _actual_deployable_files(root: Path) -> set[str]:
    actual: set[str] = set()
    try:
        for directory, directory_names, file_names in os.walk(root, followlinks=False):
            directory_path = Path(directory)
            relative_directory = directory_path.relative_to(root)
            if relative_directory == Path(".") and "backups" in directory_names:
                backups = root / "backups"
                if backups.is_symlink() or not backups.is_dir():
                    actual.add("backups")
                directory_names.remove("backups")

            for name in list(directory_names):
                candidate = directory_path / name
                if candidate.is_symlink():
                    actual.add(candidate.relative_to(root).as_posix())
                    directory_names.remove(name)

            for name in file_names:
                candidate = directory_path / name
                relative_path = candidate.relative_to(root).as_posix()
                if relative_directory == Path(".") and relative_path in _RUNTIME_FILES:
                    if candidate.is_symlink() or not candidate.is_file():
                        actual.add(relative_path)
                    continue
                actual.add(relative_path)
    except OSError:
        raise ReleaseTreeError("release tree path set mismatch") from None
    return actual


def verify_manifest(root_argument: str, manifest_argument: str) -> None:
    try:
        root = Path(root_argument).resolve(strict=True)
    except OSError:
        raise ReleaseTreeError("release root is not readable") from None
    if not root.is_dir():
        raise ReleaseTreeError("release root is not readable")

    entries = _read_manifest(Path(manifest_argument))
    _validate_runtime_state(root)
    expected_paths = {relative_path for _, _, relative_path in entries}
    if _actual_deployable_files(root) != expected_paths:
        raise ReleaseTreeError("release tree path set mismatch")

    for expected_mode, expected_digest, relative_path in entries:
        try:
            candidate = _candidate(root, relative_path)
        except ReleaseTreeError:
            raise ReleaseTreeError("release tree path set mismatch") from None
        if _git_mode(candidate) != expected_mode:
            raise ReleaseTreeError("release tree mode mismatch")
        try:
            actual_digest = _digest(candidate)
        except OSError:
            raise ReleaseTreeError("release tree content mismatch") from None
        if actual_digest != expected_digest:
            raise ReleaseTreeError("release tree content mismatch")

    sys.stdout.write("release tree verification OK\n")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=False)
    subparsers = parser.add_subparsers(dest="command", required=True)
    create = subparsers.add_parser("create", add_help=False)
    create.add_argument("--root", required=True)
    verify = subparsers.add_parser("verify", add_help=False)
    verify.add_argument("--root", required=True)
    verify.add_argument("--manifest", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        arguments = _parser().parse_args(argv)
        if arguments.command == "create":
            create_manifest(arguments.root)
        else:
            verify_manifest(arguments.root, arguments.manifest)
    except ReleaseTreeError as error:
        sys.stderr.write(f"error: {error}\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
