"""Offline developer wheel builder. Output is not production/worker acceptance.

build_wheel(source, artifacts, *, python=sys.executable) snapshots only explicit
SDK inputs into a unique private build directory. Never installs packages or
modifies the source tree. The source must be trusted Python code: this tool is
not a sandbox for executing arbitrary build projects.
"""
import argparse
from email.parser import BytesParser
from email.policy import default
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import subprocess
import sys
import tempfile
import tomllib
import zipfile


class BuildError(Exception):
    """Fixed diagnostics only; build output stays in a private build log."""


BUILD_SYSTEM = {"requires": ["setuptools==79.0.1"], "build-backend": "setuptools.build_meta"}
FIND = {"where": ["src"], "include": ["openqms_agent_sdk*"]}
DIST_INFO = "openqms_agent_sdk-0.1.0.dist-info"


def _path(value):
    path = Path(value).absolute()
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise BuildError("unsafe_path")
    return path.resolve()


def _forbidden_member(path):
    return any(part in {"tests", "test", "__pycache__"} or part.startswith("test_") or part == "conftest.py" for part in path.parts)


def _inputs(source):
    metadata_path = source / "pyproject.toml"
    readme = source / "README.md"
    package = source / "src" / "openqms_agent_sdk"
    if not source.is_dir() or not package.is_dir():
        raise BuildError("invalid_source")
    if (source / "src").is_symlink() or any(p.name.startswith(".env") for p in source.iterdir()):
        raise BuildError("unsafe_source")
    # Reject links anywhere under src without following them; no directory copy.
    paths = [metadata_path, readme]
    for base, dirs, files in os.walk(source / "src", followlinks=False):
        for name in dirs + files:
            path = Path(base) / name
            if path.is_symlink() or name.startswith(".") or _forbidden_member(path.relative_to(source)):
                raise BuildError("unsafe_source")
            if path.is_file():
                if path.suffix != ".py" or not path.is_relative_to(package):
                    raise BuildError("unsafe_source")
                paths.append(path)
    for path in paths:
        if path.is_symlink() or not path.is_file() or not stat.S_ISREG(path.stat().st_mode):
            raise BuildError("unsafe_source")
    if not (package / "__init__.py").is_file():
        raise BuildError("invalid_source")
    data = {p.relative_to(source).as_posix(): p.read_bytes() for p in sorted(paths)}
    try:
        config = tomllib.loads(data["pyproject.toml"].decode("utf-8"))
    except (ValueError, UnicodeError):
        raise BuildError("invalid_source_metadata") from None
    project = config.get("project", {})
    if (set(config) != {"build-system", "project", "tool"}
            or config.get("build-system") != BUILD_SYSTEM
            or not isinstance(project, dict)
            or set(project) - {"name", "version", "requires-python", "dependencies", "readme", "description"}
            or project.get("name") != "openqms-agent-sdk"
            or project.get("version") != "0.1.0"
            or project.get("requires-python") != ">=3.11"
            or project.get("dependencies") != []
            or project.get("readme") != "README.md"
            or config.get("tool") != {"setuptools": {"packages": {"find": FIND}}}):
        raise BuildError("invalid_source_metadata")
    return data


def validate_wheel(wheel):
    """Validate exact identity, dependency-free metadata and archive boundaries."""
    try:
        with zipfile.ZipFile(wheel) as archive:
            names = archive.namelist()
            if len(names) != len(set(names)):
                raise BuildError("invalid_wheel_members")
            for item in archive.infolist():
                name = item.filename
                path = PurePosixPath(name)
                if (not name or "\\" in name or path.is_absolute()
                        or any(p in (".", "..", "") or p.startswith(".") for p in name.split("/"))
                        or stat.S_ISLNK(item.external_attr >> 16)):
                    raise BuildError("invalid_wheel_members")
                if path.parts[0] == "openqms_agent_sdk":
                    if path.suffix != ".py" or _forbidden_member(path):
                        raise BuildError("invalid_wheel_members")
                elif path.parts[0] == DIST_INFO:
                    if len(path.parts) != 2 or path.name not in {"METADATA", "WHEEL", "RECORD", "top_level.txt"}:
                        raise BuildError("invalid_wheel_members")
                else:
                    raise BuildError("invalid_wheel_members")
            if "openqms_agent_sdk/__init__.py" not in names or not {f"{DIST_INFO}/{name}" for name in ("METADATA", "WHEEL", "RECORD")}.issubset(names):
                raise BuildError("invalid_wheel_members")
            metadata = BytesParser(policy=default).parsebytes(archive.read(f"{DIST_INFO}/METADATA"))
            expected = {"Name": "openqms-agent-sdk", "Version": "0.1.0", "Requires-Python": ">=3.11"}
            if metadata.defects or any(metadata.get_all(key) != [value] for key, value in expected.items()) or metadata.get_all("Requires-Dist"):
                raise BuildError("invalid_wheel_metadata")
    except (OSError, ValueError, KeyError, zipfile.BadZipFile):
        raise BuildError("invalid_wheel") from None
    return {"name": "openqms-agent-sdk", "version": "0.1.0", "requires_python": ">=3.11", "runtime_requirements": []}


def build_wheel(source: Path, artifacts: Path, *, python=sys.executable) -> dict:
    """Return identity, paths, SHA256 and source manifest; never raw subprocess IO."""
    try:
        source, artifacts = _path(source), _path(artifacts)
        if source == artifacts or source.is_relative_to(artifacts) or artifacts.is_relative_to(source):
            raise BuildError("overlapping_paths")
        data = _inputs(source)
        # Preserve the selected venv entry point, not its resolved base Python.
        executable = Path(python).absolute()
        if not executable.resolve(strict=True).is_file():
            raise BuildError("invalid_interpreter")
        artifacts.mkdir(parents=True, exist_ok=True)
        workspace = Path(tempfile.mkdtemp(prefix="sdk-wheel-", dir=artifacts))
        snapshot, output = workspace / "source", workspace / "wheels"
        home, temporary = workspace / "home", workspace / "tmp"
        home.mkdir(mode=0o700)
        temporary.mkdir(mode=0o700)
        env = {
            "PATH": str(executable.parent) + os.pathsep + os.defpath,
            "HOME": str(home), "TMPDIR": str(temporary),
            "PIP_CONFIG_FILE": os.devnull, "PYTHONNOUSERSITE": "1",
            "PYTHONDONTWRITEBYTECODE": "1", "PIP_NO_CACHE_DIR": "1",
            "PIP_NO_INDEX": "1", "LANG": "C.UTF-8",
        }
        query = [str(executable), "-I", "-B", "-c",
                 "from importlib.metadata import version; print(version('setuptools'))"]
        # No SDK/source imports or build code runs before the actual tool pin.
        log = workspace / "build.log"
        with log.open("xb") as stream:
            log.chmod(0o600)
            try:
                tool = subprocess.run(query, cwd=home, env=env, stdout=subprocess.PIPE,
                                      stderr=stream, timeout=30, check=False)
            except (OSError, subprocess.TimeoutExpired):
                raise BuildError("build_tool_query_failed") from None
            if tool.returncode != 0:
                raise BuildError("build_tool_query_failed")
            if tool.stdout != b"79.0.1\n":
                raise BuildError("build_tool_version_mismatch")
            snapshot.mkdir(mode=0o700)
            output.mkdir(mode=0o700)
            for name, content in data.items():
                target = snapshot / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
            command = [str(executable), "-m", "pip", "--isolated", "--disable-pip-version-check", "wheel", "--no-deps", "--no-build-isolation", "--no-index", "--wheel-dir", str(output), str(snapshot)]
            result = subprocess.run(command, cwd=snapshot, env=env, stdout=stream, stderr=subprocess.STDOUT, timeout=120, check=False)
        if result.returncode != 0:
            raise BuildError("build_failed")
        wheels = list(output.iterdir())
        if len(wheels) != 1 or wheels[0].is_symlink() or wheels[0].suffix != ".whl":
            raise BuildError("invalid_build_output")
        result = validate_wheel(wheels[0])
        result.update({
            "wheel_path": str(wheels[0]),
            "wheel_sha256": hashlib.sha256(wheels[0].read_bytes()).hexdigest(),
            "source_manifest": {name: hashlib.sha256(content).hexdigest() for name, content in data.items()},
            "build_log": str(log),
        })
        return result
    except BuildError:
        raise
    except subprocess.TimeoutExpired:
        raise BuildError("build_timeout") from None
    except (OSError, ValueError, TypeError):
        raise BuildError("build_failed") from None


class _SafeParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse's default diagnostics echo unrecognized credential arguments.
        self.exit(2, "invalid_arguments\n")


def main(argv=None):
    parser = _SafeParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = build_wheel(args.source, args.artifacts)
    except BuildError as error:
        print(str(error), file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
