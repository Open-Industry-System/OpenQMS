import dataclasses
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('_i1_helpers_identity', Path(__file__).resolve().parents[1] / 'helpers.py')
h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)
i = h.load('identity')
c = h.load('contracts')


@pytest.fixture(autouse=True)
def pure(monkeypatch):
    h.guard(monkeypatch)


def identity():
    return i.ReceiverIdentity('daemon-boot-instance', 'a'*64, 'b'*64, 'sha256:'+'c'*64,
        i.KernelObject(4, 123, b'netns-continuity'), i.UIDMap(2001, 102001, 1),
        i.KernelObject(5, 456, b'cgroup-continuity'))


def test_immutable_identity_and_exact_comparison():
    original = identity()
    assert i.same_identity(original, identity()) is True
    with pytest.raises(dataclasses.FrozenInstanceError):
        original.daemon_id = 'changed'


@pytest.mark.parametrize('key,value', [
    ('daemon_id', 'restarted-daemon'), ('container_id', 'd'*64), ('nonce', 'e'*64),
    ('image_digest', 'sha256:'+'f'*64), ('netns', i.KernelObject(4, 124, b'new')),
    ('uid_map', i.UIDMap(2001, 102002, 1)), ('cgroup', i.KernelObject(5, 457, b'new')),
    ('netns', i.KernelObject(4, 123, b'reused-inode')),
    ('cgroup', i.KernelObject(5, 456, b'reused-inode')),
])
def test_every_identity_change_refused(key, value):
    expected = identity()
    assert i.same_identity(expected, dataclasses.replace(expected, **{key: value})) is False


@pytest.mark.parametrize('bad', [None, {}, 'a'*64, True])
def test_comparison_rejects_wrong_type(bad):
    with pytest.raises(c.ContractError):
        i.same_identity(identity(), bad)
    with pytest.raises(c.ContractError):
        i.same_identity(bad, identity())


@pytest.mark.parametrize('constructor,args', [
    (i.KernelObject, (4, 123, b'')), (i.KernelObject, (4, 123, None)),
    (i.KernelObject, (True, 123, b'opaque')), (i.KernelObject, (4, 0, b'opaque')),
    (i.UIDMap, (2001, True, 1)), (i.UIDMap, (0, 102001, 1)),
    (i.UIDMap, (2001, 0, 1)), (i.UIDMap, (2001, 102001, 0)),
])
def test_invalid_or_unproven_kernel_identity(constructor, args):
    with pytest.raises(c.ContractError):
        constructor(*args)


@pytest.mark.parametrize('key,value', [('container_id', 'short'), ('daemon_id', ''),
    ('nonce', 'prefix'), ('image_digest', 'image:latest'), ('uid_map', {}),
    ('cgroup', '/historical/path'), ('netns', 123)])
def test_identity_no_path_name_prefix_or_wrong_types(key, value):
    with pytest.raises(c.ContractError):
        dataclasses.replace(identity(), **{key: value})
