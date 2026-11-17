#!/usr/bin/python3
"""Single installed entry, usable with python -I -S; no cwd/env import path."""
import os
from pathlib import Path
import re
import stat
import sys

def harden_process():
    """Management processes may hold configuration; neither cores nor ptrace dumps."""
    try:
        if sys.platform!='linux': return False
        import ctypes
        import resource
        resource.setrlimit(resource.RLIMIT_CORE,(0,0))
        if resource.getrlimit(resource.RLIMIT_CORE)!=(0,0): return False
        libc=ctypes.CDLL(None,use_errno=True)
        prctl=libc.prctl
        prctl.argtypes=[ctypes.c_int,ctypes.c_ulong,ctypes.c_ulong,ctypes.c_ulong,ctypes.c_ulong]
        prctl.restype=ctypes.c_int
        if prctl(4,0,0,0,0)!=0: return False  # PR_SET_DUMPABLE
        return prctl(3,0,0,0,0)==0          # PR_GET_DUMPABLE
    except Exception:
        return False

def main(argv=None):
    try:
        if not harden_process(): raise ValueError('entry_invalid')
        entry=Path(os.path.abspath(__file__))
        root=entry.parents[2]
        # Verify all components before trusting imports. ROOT is the one private
        # deployment directory, never a caller-supplied option.
        if os.getuid()!=0 or '..' in str(entry).split('/'): return 1
        fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:
            for component in entry.parts[1:-1]:
                new=os.open(component,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
                os.close(fd);fd=new
                info=os.fstat(fd)
                if info.st_uid!=0 or info.st_mode&0o022: return 1
            handle=os.open(entry.name,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=fd)
            try:
                info=os.fstat(handle)
                if not stat.S_ISREG(info.st_mode) or info.st_uid!=0 or info.st_nlink!=1 or info.st_mode&0o022:return 1
            finally:os.close(handle)
        finally:os.close(fd)
        if stat.S_IMODE(root.stat().st_mode)!=0o700:return 1
        supplied=list(sys.argv[1:] if argv is None else argv)
        if len(supplied)!=3 or supplied[0] not in ('launch','controller','watchdog','stop','maintain') or supplied[1]!='--nonce':return 1
        role,nonce=supplied[0],supplied[2]
        if re.fullmatch('[a-f0-9]{64}',nonce) is None:return 1
        sys.path.insert(0,str(root))
        from agent_d4_isolation.runtime_supervisor import validate_entry,launch_session,stop_session,maintain
        validate_entry(root,entry)
        if role=='controller':
            from agent_d4_isolation.runtime_controller import main as controller
            return controller(['--nonce',nonce])
        if role=='watchdog':
            from agent_d4_isolation.watchdog_main import run
            return run(root,nonce)
        if role=='launch': result=launch_session(root,nonce)
        elif role=='stop': result=stop_session(root,nonce)
        else: result=maintain(root,nonce)
        print(result)
        return 0 if result=='isolation_terminated' else 1
    except BaseException:
        print('isolation_unknown')
        return 1
if __name__=='__main__':raise SystemExit(main())
