"""Actual custom-seccomp receiver stress; no database or platform authority."""
import importlib.util
import json
import os
from pathlib import Path
import shlex
import hashlib
import pytest

HERE=Path(__file__).resolve().parent


def _probe():
    spec=importlib.util.spec_from_file_location('_stress_local',HERE/'runtime_stress_probe.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('payload,reason',[
    ("import os,time;os.write(1,b'x'*8192);time.sleep(2)",'exec_output_limit'),
    ("import os,time;os.write(1,b'partial');time.sleep(2)",'exec_capture_deadline')])
def test_local_exec_capture_bounds_bytes_and_partial_line_time(payload,reason):
    import subprocess,sys,time
    probe=_probe()
    child=subprocess.Popen([sys.executable,'-I','-S','-B','-c',payload],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    try:
        with pytest.raises(RuntimeError,match=reason):
            probe.capture(child,time.monotonic_ns()+500_000_000,first_line=True)
    finally:
        child.kill();child.wait(timeout=1);child.stdout.close();child.stderr.close()


def test_local_combined_attack_never_overflows_either_stream_alone(monkeypatch,capsys):
    import os,time
    probe=_probe();writes={71:[],72:[]}
    class Finished(Exception):pass
    monkeypatch.setattr(os,'open',lambda path,flags:71 if path.endswith('/1') else 72)
    monkeypatch.setattr(os,'write',lambda fd,data:(writes[fd].append(data) or len(data)))
    monkeypatch.setattr(os.path,'exists',lambda path:True)
    def pause(seconds):
        assert seconds==30
        raise Finished()
    monkeypatch.setattr(time,'sleep',pause)
    with pytest.raises(Finished):exec(compile(probe.program('combined'),'<controlled-output>','exec'),{})
    sizes=[sum(map(len,rows)) for rows in writes.values()]
    assert all(0<size<4096 for size in sizes) and sum(sizes)>4096
    assert capsys.readouterr().out=='streams_verified\n'


@pytest.mark.parametrize('case',('combined','flood','limits','memory'))
def test_real_receiver_output_and_resource_pressure(remote,case):
    spec=importlib.util.spec_from_file_location('_stress_bundle',HERE/'test_runtime_wiring.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    bundle,digest=module._package_bundle()
    values=dict(PACKAGE_B64=bundle,PACKAGE_SHA256=digest,STRESS_CASE=case,
                STRESS_DIAGNOSTIC=os.environ.get('OPENQMS_STRESS_DIAGNOSTIC')=='1',
                STRESS_PROBE_SHA256=hashlib.sha256((HERE/'runtime_stress_probe.py').read_bytes()).hexdigest(),
                WIRING_PROBE_SOURCE=(HERE/'runtime_wiring_probe.py').read_text(),
                FAULT_PROBE_SOURCE=(HERE/'runtime_faults_probe.py').read_text(),
                WIRE_FIXTURE_SOURCE=(HERE.parents[3]/'backend/tests/e2e/d4_text_wire_fixture.py').read_text())
    source=''.join(k+'='+repr(v)+'\n' for k,v in values.items())+(HERE/'runtime_stress_probe.py').read_text()
    image=os.environ.get('OPENQMS_ISOLATION_RECEIVER_IMAGE');assert image
    out=remote('sudo -n python3 -I -S -B - '+shlex.quote(image)+" <<'STRESS'\n"+source+'\nSTRESS\n',timeout=180,check=False)
    print(out)
    rows=[json.loads(line) for line in out.splitlines() if line.startswith('{')]
    assert len(rows)==1,out
    row=rows[0]
    assert row['case']==case and row['verified'] and row['resources_cleaned'],row
    assert row['receiver_stopped'] and row['observer_cgroup_empty'] and row['api_survived'],row
    assert row['journal_summary']['closed_by']=='reclaim_verified',row
    assert 'runtime_stress_verified:'+case in out.splitlines(),out
