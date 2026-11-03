"""Developer build-tool contracts; fixture builds are not current SDK acceptance."""
import importlib.util
import socket
from pathlib import Path

import pytest

BUILDER = Path(__file__).resolve().parents[2] / "scripts" / "build-wheel.py"


@pytest.fixture(autouse=True)
def deny_network(monkeypatch):
    attempts = []

    def denied(*args, **kwargs):
        attempts.append(True)
        raise AssertionError("network forbidden")

    for name in ("connect", "connect_ex", "bind"):
        monkeypatch.setattr(socket.socket, name, denied)
    for name in ("getaddrinfo", "gethostbyname", "gethostbyname_ex", "gethostbyaddr", "create_connection"):
        monkeypatch.setattr(socket, name, denied)
    yield
    assert not attempts


def builder():
    assert BUILDER.is_file(), "wheel builder is not implemented"
    spec = importlib.util.spec_from_file_location("sdk_wheel_builder", BUILDER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def sample_sdk(tmp_path):
    source = tmp_path / "sample-sdk"
    package = source / "src" / "openqms_agent_sdk"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text('__version__ = "0.1.0"\n')
    (source / "README.md").write_text("# Fixture-only SDK\n")
    (source / "pyproject.toml").write_text('''[build-system]
requires = ["setuptools==79.0.1"]
build-backend = "setuptools.build_meta"
[project]
name = "openqms-agent-sdk"
version = "0.1.0"
requires-python = ">=3.11"
readme = "README.md"
dependencies = []
[tool.setuptools.packages.find]
where = ["src"]
include = ["openqms_agent_sdk*"]
''')
    return source


def test_fixture_offline_wheel_metadata(sample_sdk, tmp_path):
    import hashlib
    module = builder()
    before = {p.relative_to(sample_sdk).as_posix(): p.read_bytes() for p in sample_sdk.rglob("*") if p.is_file()}
    result = module.build_wheel(sample_sdk, tmp_path / "artifacts")
    assert result["name"] == "openqms-agent-sdk"
    assert result["version"] == "0.1.0"
    assert result["requires_python"] == ">=3.11"
    assert result["runtime_requirements"] == []
    wheel = Path(result["wheel_path"])
    assert wheel.is_file() and wheel.suffix == ".whl"
    assert result["wheel_sha256"] == hashlib.sha256(wheel.read_bytes()).hexdigest()
    assert result["source_manifest"] == {name: hashlib.sha256(data).hexdigest() for name, data in before.items()}
    assert before == {p.relative_to(sample_sdk).as_posix(): p.read_bytes() for p in sample_sdk.rglob("*") if p.is_file()}


def make_wheel(path, *, metadata=None, extra=None):
    import zipfile
    info = "openqms_agent_sdk-0.1.0.dist-info/"
    entries = {
        "openqms_agent_sdk/__init__.py": '__version__ = "0.1.0"\n',
        info + "METADATA": metadata or "Metadata-Version: 2.4\nName: openqms-agent-sdk\nVersion: 0.1.0\nRequires-Python: >=3.11\n\n",
        info + "WHEEL": "Wheel-Version: 1.0\nTag: py3-none-any\n",
        info + "RECORD": "",
    }
    entries.update(extra or {})
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in entries.items():
            archive.writestr(name, content)


@pytest.mark.parametrize("line", ["Name: wrong", "Version: 0.2.0", "Requires-Python: >=3.10", "Requires-Dist: forbidden"])
def test_executable_wheel_metadata_rejection(tmp_path, line):
    module = builder()
    wheel = tmp_path / "bad.whl"
    metadata = "Metadata-Version: 2.4\nName: openqms-agent-sdk\nVersion: 0.1.0\nRequires-Python: >=3.11\n"
    key = line.split(":")[0]
    metadata = "\n".join(row for row in metadata.splitlines() if not row.startswith(key + ":")) + "\n" + line + "\n\n"
    make_wheel(wheel, metadata=metadata)
    with pytest.raises(module.BuildError, match="invalid_wheel_metadata"):
        module.validate_wheel(wheel)


@pytest.mark.parametrize("name", ["../escape.py", "/absolute.py", "other/__init__.py", "tests/test_x.py", "openqms_agent_sdk/.env", "openqms_agent_sdk/a.pyc", "openqms_agent_sdk/tests/test_x.py", "openqms_agent_sdk/test_x.py", "openqms_agent_sdk\\bad.py", "other-1.dist-info/METADATA"])
def test_wheel_member_boundaries(tmp_path, name):
    module = builder()
    wheel = tmp_path / "bad.whl"
    make_wheel(wheel, extra={name: "fixture-only"})
    with pytest.raises(module.BuildError, match="invalid_wheel_members"):
        module.validate_wheel(wheel)


@pytest.mark.parametrize("suffix", ["same", "child", "parent"])
def test_source_artifact_overlap_rejected(sample_sdk, suffix):
    module = builder()
    output = {"same": sample_sdk, "child": sample_sdk / "output", "parent": sample_sdk.parent}[suffix]
    with pytest.raises(module.BuildError, match="overlapping_paths"):
        module.build_wheel(sample_sdk, output)
    assert not (sample_sdk / "output").exists()


@pytest.mark.parametrize("kind", ["source", "src", "file", "output"])
def test_symlinks_rejected(sample_sdk, tmp_path, kind):
    module = builder()
    source, output = sample_sdk, tmp_path / "artifacts"
    if kind == "source":
        source = tmp_path / "source-link"
        source.symlink_to(sample_sdk, target_is_directory=True)
    elif kind == "src":
        source = tmp_path / "linked-sdk"
        source.mkdir()
        for name in ("pyproject.toml", "README.md"):
            (source / name).write_bytes((sample_sdk / name).read_bytes())
        (source / "src").symlink_to(sample_sdk / "src", target_is_directory=True)
    elif kind == "file":
        (sample_sdk / "src/openqms_agent_sdk/link.py").symlink_to(sample_sdk / "README.md")
    else:
        target = tmp_path / "target"
        target.mkdir()
        output.symlink_to(target, target_is_directory=True)
    with pytest.raises(module.BuildError, match="unsafe"):
        module.build_wheel(source, output)


@pytest.mark.parametrize("name", ["src/openqms_agent_sdk/.env", ".env", "src/openqms_agent_sdk/tests/test_x.py"])
def test_credential_and_test_source_inputs_rejected(sample_sdk, tmp_path, name):
    module = builder()
    path = sample_sdk / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("fixture-only-not-a-real-credential")
    with pytest.raises(module.BuildError, match="unsafe_source"):
        module.build_wheel(sample_sdk, tmp_path / "artifacts")


def test_curated_subprocess_and_private_failure_log(sample_sdk, tmp_path, monkeypatch, capsys):
    import os
    from types import SimpleNamespace
    module = builder()
    monkeypatch.setenv("HTTP_PROXY", "private-proxy")
    monkeypatch.setenv("PIP_INDEX_URL", "private-index")
    monkeypatch.setenv("MODEL_TOKEN", "private-token")
    monkeypatch.setenv("PYTHONPATH", "private-path")
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        assert "shell" not in kwargs
        env = kwargs["env"]
        assert env["PIP_CONFIG_FILE"] == os.devnull
        assert not {"HTTP_PROXY", "PIP_INDEX_URL", "MODEL_TOKEN", "PYTHONPATH"}.intersection(env)
        if command[1:4] == ["-I", "-B", "-c"]:
            assert kwargs["cwd"] == Path(env["HOME"])
            return SimpleNamespace(returncode=0, stdout=b"79.0.1\n")
        assert command[1:9] == ["-m", "pip", "--isolated", "--disable-pip-version-check", "wheel", "--no-deps", "--no-build-isolation", "--no-index"]
        assert Path(env["HOME"]).parent == kwargs["cwd"].parent
        kwargs["stdout"].write(b"fixture-only-sensitive-build-output")
        return SimpleNamespace(returncode=9)

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    with pytest.raises(module.BuildError, match="^build_failed$"):
        module.build_wheel(sample_sdk, tmp_path / "artifacts")
    assert len(calls) == 2
    log = next((tmp_path / "artifacts").glob("sdk-wheel-*/build.log"))
    assert log.stat().st_mode & 0o777 == 0o600
    assert log.read_bytes() == b"fixture-only-sensitive-build-output"
    assert "sensitive" not in str(capsys.readouterr())


def test_cli_json_and_failure_exit(sample_sdk, tmp_path, monkeypatch, capsys):
    import json
    module = builder()
    expected = {"name": "fixture-only", "runtime_requirements": []}
    monkeypatch.setattr(module, "build_wheel", lambda *a, **kw: expected)
    assert module.main(["--source", str(sample_sdk), "--artifacts", str(tmp_path / "artifacts")]) == 0
    output = capsys.readouterr()
    assert json.loads(output.out) == expected and output.err == ""

    def failed(*args, **kwargs):
        raise module.BuildError("build_failed")

    monkeypatch.setattr(module, "build_wheel", failed)
    assert module.main(["--source", str(sample_sdk), "--artifacts", str(tmp_path / "artifacts")]) == 1
    output = capsys.readouterr()
    assert output.out == "" and output.err == "build_failed\n"


def test_cli_rejects_credentials_without_echo(capsys):
    module = builder()
    with pytest.raises(SystemExit) as caught:
        module.main(["--source", "fixture-source", "--artifacts", "fixture-output", "--token", "fixture-private-token"])
    assert caught.value.code != 0
    output = capsys.readouterr()
    assert output.out == "" and "fixture-private-token" not in output.err


def test_unique_artifact_children_and_explicit_input_copy(sample_sdk, tmp_path, monkeypatch):
    from types import SimpleNamespace
    module = builder()
    ignored = sample_sdk / "support"
    ignored.mkdir()
    (ignored / "not-an-sdk-input.txt").write_text("fixture-only")
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    marker = artifacts / "user-owned.txt"
    marker.write_text("preserve")
    copies = []

    def fake_run(command, **kwargs):
        if command[1:4] == ["-I", "-B", "-c"]:
            return SimpleNamespace(returncode=0, stdout=b"79.0.1\n")
        output = Path(command[command.index("--wheel-dir") + 1])
        snapshot = Path(command[-1])
        copies.append({p.relative_to(snapshot).as_posix() for p in snapshot.rglob("*") if p.is_file()})
        make_wheel(output / "fixture.whl")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    first = module.build_wheel(sample_sdk, artifacts)
    second = module.build_wheel(sample_sdk, artifacts)
    assert first["wheel_path"] != second["wheel_path"]
    assert marker.read_text() == "preserve"
    assert copies == [{"pyproject.toml", "README.md", "src/openqms_agent_sdk/__init__.py"}] * 2
    assert set(first) == {"name", "version", "requires_python", "runtime_requirements", "wheel_path", "wheel_sha256", "source_manifest", "build_log"}


@pytest.mark.parametrize("failure", ["timeout", "oserror", "missing", "extra"])
def test_subprocess_failures_are_non_success_safe_errors(sample_sdk, tmp_path, monkeypatch, failure):
    from types import SimpleNamespace
    module = builder()

    def fake_run(command, **kwargs):
        if command[1:4] == ["-I", "-B", "-c"]:
            return SimpleNamespace(returncode=0, stdout=b"79.0.1\n")
        if failure == "timeout":
            raise module.subprocess.TimeoutExpired(["fixture-private-command"], 1, output=b"private-output")
        if failure == "oserror":
            raise OSError("fixture-private-os-error")
        if failure == "extra":
            output = Path(command[command.index("--wheel-dir") + 1])
            make_wheel(output / "one.whl")
            make_wheel(output / "two.whl")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    with pytest.raises(module.BuildError) as caught:
        module.build_wheel(sample_sdk, tmp_path / "artifacts")
    assert "private" not in str(caught.value) + repr(caught.value.args)


def test_duplicate_or_symlink_wheel_members_rejected(tmp_path):
    import stat
    import warnings
    import zipfile
    module = builder()
    wheel = tmp_path / "duplicate.whl"
    make_wheel(wheel)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        with zipfile.ZipFile(wheel, "a") as archive:
            archive.writestr("openqms_agent_sdk/__init__.py", "duplicate")
    with pytest.raises(module.BuildError, match="invalid_wheel_members"):
        module.validate_wheel(wheel)
    wheel = tmp_path / "symlink.whl"
    make_wheel(wheel)
    with zipfile.ZipFile(wheel, "a") as archive:
        entry = zipfile.ZipInfo("openqms_agent_sdk/link.py")
        entry.create_system = 3
        entry.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(entry, "../outside")
    with pytest.raises(module.BuildError, match="invalid_wheel_members"):
        module.validate_wheel(wheel)


@pytest.mark.parametrize("version,code,diagnostic", [(b"82.0.0\n", 0, "build_tool_version_mismatch"), (b"", 1, "build_tool_query_failed"), (b"private-invalid-output", 0, "build_tool_version_mismatch")])
def test_selected_interpreter_build_version_checked_before_pip(sample_sdk, tmp_path, monkeypatch, capsys, version, code, diagnostic):
    import os
    import sys
    from types import SimpleNamespace
    module = builder()
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        if command[1:3] == ["-m", "pip"]:
            output = Path(command[command.index("--wheel-dir") + 1])
            make_wheel(output / "wrong-tool.whl")
            return SimpleNamespace(returncode=0)
        assert command[0] == sys.executable
        assert command[1:4] == ["-I", "-B", "-c"]
        assert "importlib.metadata" in command[4] and "setuptools" in command[4]
        assert "openqms_agent_sdk" not in command[4]
        env = kwargs["env"]
        assert env["PIP_CONFIG_FILE"] == os.devnull and env["PIP_NO_INDEX"] == "1"
        assert not {"PYTHONPATH", "PIP_INDEX_URL", "HTTP_PROXY", "MODEL_TOKEN"}.intersection(env)
        assert kwargs["cwd"] == Path(env["HOME"])
        return SimpleNamespace(returncode=code, stdout=version)

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    with pytest.raises(module.BuildError, match="^" + diagnostic + "$"):
        module.build_wheel(sample_sdk, tmp_path / "artifacts")
    assert len(calls) == 1 and calls[0][1:4] == ["-I", "-B", "-c"]
    assert "private" not in str(capsys.readouterr())


@pytest.mark.parametrize("failure", ["oserror", "timeout"])
def test_query_exception_never_builds_or_echoes(sample_sdk, tmp_path, monkeypatch, capsys, failure):
    module = builder()
    calls = []

    def failed_query(command, **kwargs):
        calls.append(command)
        assert command[1:4] == ["-I", "-B", "-c"]
        if failure == "timeout":
            raise module.subprocess.TimeoutExpired(["fixture-private"], 1, output=b"fixture-private")
        raise OSError("fixture-private")

    monkeypatch.setattr(module.subprocess, "run", failed_query)
    with pytest.raises(module.BuildError, match="^build_tool_query_failed$"):
        module.build_wheel(sample_sdk, tmp_path / "artifacts")
    assert len(calls) == 1
    assert not list((tmp_path / "artifacts").glob("sdk-wheel-*/source"))
    assert "fixture-private" not in str(capsys.readouterr())


def test_explicit_interpreter_entry_not_replaced_by_resolved_base(sample_sdk, tmp_path, monkeypatch):
    import sys
    from types import SimpleNamespace
    module = builder()
    entry = tmp_path / "selected-venv-python"
    entry.symlink_to(sys.executable)
    calls = []

    def query(command, **kwargs):
        calls.append(command)
        assert command[0] == str(entry) and command[1:4] == ["-I", "-B", "-c"]
        assert kwargs["env"]["PATH"].split(module.os.pathsep)[0] == str(entry.parent)
        return SimpleNamespace(returncode=0, stdout=b"82.0.0\n")

    monkeypatch.setattr(module.subprocess, "run", query)
    with pytest.raises(module.BuildError, match="^build_tool_version_mismatch$"):
        module.build_wheel(sample_sdk, tmp_path / "artifacts", python=entry)
    assert len(calls) == 1


def test_dependency_metadata_rejected_before_build(sample_sdk, tmp_path):
    module = builder()
    project = sample_sdk / "pyproject.toml"
    project.write_text(project.read_text().replace("dependencies = []", 'dependencies = ["unexpected-runtime"]'))
    with pytest.raises(module.BuildError, match="invalid_source_metadata"):
        module.build_wheel(sample_sdk, tmp_path / "artifacts")
