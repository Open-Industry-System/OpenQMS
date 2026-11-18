"""Deterministically bundle the pure SDK into one sandbox-approved artifact.

The loader executes only frozen SDK sources embedded in this artifact. It never
reads package code from disk, extracts a zip, or evaluates protocol contents.
"""
import argparse
import hashlib
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
SDK=ROOT/'sdk/python/src/openqms_agent_sdk'
OUTPUT=ROOT/'backend/examples/d4_candidate_agent.py'
MAIN=ROOT/'backend/examples/d4_candidate_agent_main.py'


def render():
    expected={'__init__','_codec','_deadline','_transport','client','errors','models'}
    if {path.stem for path in SDK.glob('*.py')}!=expected:
        raise SystemExit('Unexpected SDK module list')
    sources={}
    manifest={}
    for path in sorted(SDK.glob('*.py')):
        module='openqms_agent_sdk' + ('' if path.stem=='__init__' else '.'+path.stem)
        source=path.read_text(encoding='utf-8')
        sources[module]=source
        manifest[module]=hashlib.sha256(source.encode('utf-8')).hexdigest()
    loader='''
import importlib.abc
import importlib.util
import sys

if set(_SDK_MANIFEST)!=set(_SDK_SOURCES):
    raise ImportError('Approved module manifest mismatch')

class _FrozenSDK(importlib.abc.MetaPathFinder,importlib.abc.Loader):
    def find_spec(self,fullname,path=None,target=None):
        if fullname in _SDK_SOURCES:
            return importlib.util.spec_from_loader(fullname,self,is_package=fullname=='openqms_agent_sdk')
        if fullname.startswith('openqms_agent_sdk.'):
            raise ImportError('Module outside approved bundle')
        return None
    def create_module(self,spec):
        return None
    def exec_module(self,module):
        source=_SDK_SOURCES[module.__name__]
        import hashlib
        if hashlib.sha256(source.encode('utf-8')).hexdigest()!=_SDK_MANIFEST[module.__name__]:
            raise ImportError('Approved bundle mismatch')
        module.__file__='<embedded:'+module.__name__+'>'
        exec(compile(source,module.__file__,'exec'),module.__dict__)

sys.meta_path.insert(0,_FrozenSDK())
'''
    return ('"""Generated D4 SDK artifact; rebuild with sdk/python/scripts/build-d4-agent.py.\n'
        'ExecutorApproval must pin these complete bytes, including every SDK module.\n"""\n'
        +'_SDK_MANIFEST = '+repr(manifest)+'\n_SDK_SOURCES = '+repr(sources)+'\n'+loader+'\n'+MAIN.read_text(encoding='utf-8'))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--check',action='store_true')
    args=parser.parse_args()
    result=render()
    if args.check:
        if not OUTPUT.is_file() or OUTPUT.read_text(encoding='utf-8')!=result:
            raise SystemExit('D4 SDK artifact is stale')
    else:
        OUTPUT.write_text(result,encoding='utf-8')
    print('artifact_sha256='+hashlib.sha256(result.encode('utf-8')).hexdigest())


if __name__=='__main__':
    main()
