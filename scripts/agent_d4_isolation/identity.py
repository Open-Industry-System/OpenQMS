"""Compare immutable, currently trusted identity facts; collect nothing.

These types DO NOT authenticate cgroups, Docker responses or kernel objects.
A continuity token must come from a trusted collector retaining an object/birth
reference and revalidating it NOW. Historical strings, path+inode equality, and
caller-invented tokens cannot establish that precondition. When the collector
cannot prove continuity (including possible inode reuse), it must supply no
identity; comparisons then reject. Implementing that collector is NOT I1.
"""
from dataclasses import dataclass
import re

from .contracts import require


@dataclass(frozen=True, slots=True)
class UIDMap:
    """One mapping line for the receiver's own UID, not the whole uid_map file.

    A container's first line is typically `0 <host> <len>`, which this type
    cannot represent; I3 must translate the real mapping into the receiver's
    single effective (inside, host, length) triple before comparing.
    """
    inside_uid: int
    host_uid: int
    length: int

    def __post_init__(self):
        require(all(type(value) is int and value > 0 for value in
                    (self.inside_uid, self.host_uid, self.length)))


@dataclass(frozen=True, slots=True)
class KernelObject:
    device: int
    inode: int
    continuity_token: bytes

    def __post_init__(self):
        require(type(self.device) is int and self.device >= 0)
        require(type(self.inode) is int and self.inode > 0)
        require(type(self.continuity_token) is bytes and bool(self.continuity_token))


@dataclass(frozen=True, slots=True)
class ReceiverIdentity:
    # An instance identity including daemon restart continuity, NOT just the
    # stable Docker info.ID. Only "non-empty str" is checked here, so a short
    # 12-char container-style ID or a path would also pass: I3 must embed a
    # per-instance fact (for example the boot ID) and must never pass info.ID.
    daemon_id: str
    container_id: str
    nonce: str
    image_digest: str
    netns: KernelObject
    uid_map: UIDMap
    cgroup: KernelObject

    def __post_init__(self):
        require(type(self.daemon_id) is str and bool(self.daemon_id))
        for value in (self.container_id, self.nonce):
            require(type(value) is str and re.fullmatch(r'[a-f0-9]{64}', value) is not None)
        require(type(self.image_digest) is str and re.fullmatch(r'sha256:[a-f0-9]{64}', self.image_digest) is not None)
        require(type(self.netns) is KernelObject and type(self.cgroup) is KernelObject)
        require(type(self.uid_map) is UIDMap)


def same_identity(expected, current):
    """Equality only, conditional on both inputs being CURRENT trusted facts."""
    require(type(expected) is ReceiverIdentity and type(current) is ReceiverIdentity)
    return expected == current
