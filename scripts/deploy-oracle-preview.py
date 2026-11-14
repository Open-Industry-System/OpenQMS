#!/usr/bin/env python3
"""Trusted closed-PR cleanup runner. Execute only from protected default branch.
"""
import importlib.util
import os
from pathlib import Path
import re
import select
import shlex
import subprocess
import sys

def closed(pr):
    spec = importlib.util.spec_from_file_location('gate', Path(__file__).with_name('oracle-ci-gate.py'))
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)
    metadata = gate.GitHub(os.environ['GITHUB_REPOSITORY']).get('/pulls/' + pr)
    if metadata.get('state') != 'closed' or metadata.get('number') != int(pr):
        raise ValueError('PR must currently be closed for cleanup')

def main():
    if len(sys.argv) != 3 or sys.argv[1] != '--cleanup':
        raise ValueError('only --cleanup PR is supported; deploy with shared release runner')
    pr = sys.argv[2]
    if not re.fullmatch(r'[1-9][0-9]{0,8}', pr): raise ValueError('invalid PR')
    target = os.environ['ORACLE_SSH_TARGET']
    if not re.fullmatch(r'[a-z_][a-z0-9_-]*@[a-zA-Z0-9.-]+', target) or target.split('@')[0] in {'root', 'ubuntu'}: raise ValueError('invalid SSH target')
    ssh = ['ssh', '-T', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes', '-o', 'ConnectTimeout=20', '-o', 'UserKnownHostsFile=' + os.environ['ORACLE_KNOWN_HOSTS'], '-i', os.environ['ORACLE_SSH_KEY'], target]
    closed(pr)
    process = subprocess.Popen(ssh + [shlex.join(['preview', 'cleanup', pr])], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    try:
        if not select.select([process.stdout], [], [], 120)[0] or process.stdout.readline().strip() != 'READY':
            raise ValueError('cleanup host not ready')
        closed(pr)
        process.stdin.write('CLEANUP\n')
        process.stdin.flush()
        process.stdin.close()
        if process.wait(timeout=120) != 0: raise ValueError('cleanup failed')
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=30)
    return

if __name__ == '__main__': main()
