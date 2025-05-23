from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import libvirt


class DomainStateEnum(Enum):
    NOSTATE = 0
    RUNNING = 1
    BLOCKED = 2
    PAUSED = 3
    SHUTDOWN = 4
    SHUTOFF = 5
    CRASHED = 6
    PMSUSPENDED = 7
    LAST = 8


@dataclass(frozen=True)
class DomainInfo:
    name: str
    UUID: str
    state: DomainStateEnum
    disks: list[Path]
    ip_address: str | None = None
    os_id: str | None = None
    os_version_id: str | None = None


@dataclass(frozen=True)
class PoolInfo:
    name: str
    UUID: str
    path: Path
    volumes: list[libvirt.virStorageVol]


@dataclass(frozen=True)
class VirtInspectorData:
    osinfo: str | None = None
    distro: str | None = None
    major_version: str | None = None
    minor_version: str | None = None
    name: str | None = None
