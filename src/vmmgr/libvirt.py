import functools
import sys
from operator import itemgetter
from pathlib import Path
from typing import Any
from xml.dom import minidom

import libvirt
from libvirt import libvirtError

from vmmgr.constants import IMAGE_EXTENSIONS
from vmmgr.constants import VMMGR_POOL_NAME
from vmmgr.constants import VMMGR_TEMPLATE_IMAGES_POOLS
from vmmgr.types import DomainInfo
from vmmgr.types import DomainStateEnum
from vmmgr.types import PoolInfo


@functools.cache
def _libvirt_connection():
    conn = libvirt.open()
    return conn


def _get_domain_ip_address(guest_info) -> str | None:
    addresses = []
    if_data = {k.removeprefix("if."): v for k, v in guest_info.items() if k.startswith("if.")}
    if_ids = set()
    for key in if_data.keys():
        key_id, _, _ = key.partition(".")
        if_ids.add(key_id)

    for if_id in if_ids:
        if_name = if_data.get(f"{if_id}.name")
        if if_name == "lo":
            continue
        interface_data = {k: v for k, v in if_data.items() if k.startswith(f"{if_id}.")}
        for key, value in interface_data.items():
            if not key.endswith(".addr"):
                continue
            prefix, _, _ = key.rpartition(".")
            ip_type = interface_data.get(f"{prefix}.type")
            addresses.append((value, ip_type))

    addresses.sort(key=itemgetter(1))
    try:
        return addresses[0][0]
    except IndexError:
        return None


def _get_domain_guest_data(domain: libvirt.virDomain) -> dict[str, Any]:
    state, _ = domain.state()
    state = DomainStateEnum(state)
    if state != DomainStateEnum.RUNNING:
        return {}

    try:
        guest_info = domain.guestInfo()
    except libvirtError:
        return {}
    return {
        "ip_address": _get_domain_ip_address(guest_info),
        "os_id": guest_info.get("os.id"),
        "os_version_id": guest_info.get("os.version-id"),
    }


def _get_domain_disks(domain_data) -> list[Path]:
    disks = []
    for key, value in domain_data.items():
        if key.startswith("block.") and str(value).startswith("/"):
            disks.append(Path(value))
    return disks


@functools.cache
def get_domains_info() -> list[DomainInfo]:
    conn = _libvirt_connection()
    domains = []
    for domain, domain_data in conn.getAllDomainStats():
        domain_guest_data = _get_domain_guest_data(domain)
        disks = _get_domain_disks(domain_data)
        domain_obj = DomainInfo(
            name=domain.name(),
            UUID=domain.UUIDString(),
            state=DomainStateEnum(domain_data.get("state.state", 0)),
            disks=disks,
            ip_address=domain_guest_data.get("ip_address"),
            os_id=domain_guest_data.get("os_id"),
            os_version_id=domain_guest_data.get("os_version_id"),
        )
        domains.append(domain_obj)
    return domains


def _get_pool_path(xml: str) -> Path:
    tree = minidom.parseString(xml)
    for path_node in tree.getElementsByTagName("path"):
        for child in path_node.childNodes:
            if child.nodeType == child.TEXT_NODE:
                return Path(child.nodeValue)
    raise libvirtError("<path> element not found")


def _get_pool_volumes(pool: libvirt.virStoragePool) -> list[libvirt.virStorageVol]:
    volumes = []
    all_volumes = pool.listAllVolumes()
    for volume in all_volumes:
        p = Path(volume.path())
        extension = p.suffix.lower().removeprefix(".")
        if extension not in IMAGE_EXTENSIONS:
            continue
        volumes.append(volume)
    return volumes


@functools.cache
def get_pools_info() -> list[PoolInfo]:
    conn = _libvirt_connection()
    pools = []
    for pool in conn.listAllStoragePools():
        try:
            path = _get_pool_path(pool.XMLDesc())
        except libvirtError:
            continue
        pool_obj = PoolInfo(
            name=pool.name(),
            UUID=pool.UUIDString(),
            path=path,
            volumes=_get_pool_volumes(pool),
        )
        pools.append(pool_obj)
    return pools


def get_template_volumes() -> dict[str, PoolInfo]:
    pools = get_pools_info()
    allowed_pools = [name.strip() for name in VMMGR_TEMPLATE_IMAGES_POOLS.split(",")]
    template_volumes = {}

    for pool in pools:
        if pool.name not in allowed_pools:
            continue
        for volume in pool.volumes:
            key = volume.path()
            template_volumes[key] = pool

    return template_volumes


def get_vmmgr_pool() -> PoolInfo:
    all_pools = get_pools_info()
    vmmgr_pool = next((p for p in all_pools if p.name == VMMGR_POOL_NAME), None)
    if not vmmgr_pool:
        msg = (
            f"libvirt pool '{VMMGR_POOL_NAME}' not found. "
            "Did you change VMMGR_POOL environment variable?"
        )
        sys.exit(msg)
    return vmmgr_pool


def get_vmmgr_managed_vms():
    vmmgr_pool = get_vmmgr_pool()
    vmmgr_volumes = set([Path(v.path()) for v in vmmgr_pool.volumes])
    vms = get_domains_info()
    filtered = [vm for vm in vms if set(vm.disks).intersection(vmmgr_volumes)]
    return filtered
