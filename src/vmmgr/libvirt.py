import functools
import itertools
import sys
import xml.etree.ElementTree as ET
from datetime import datetime
from operator import itemgetter
from pathlib import Path
from urllib.parse import urlparse

import libvirt
from libvirt import libvirtError

from vmmgr.constants import IMAGE_EXTENSIONS
from vmmgr.constants import LIBVIRT_CONNECTION_URIS
from vmmgr.constants import LIBVIRT_XML_NAMESPACES
from vmmgr.constants import VMMGR_POOL_NAME
from vmmgr.constants import VMMGR_TEMPLATE_IMAGES_POOLS
from vmmgr.types import DhcpLeaseInfo
from vmmgr.types import DomainInfo
from vmmgr.types import DomainStateEnum
from vmmgr.types import PoolInfo
from vmmgr.types import VmmgrException


@functools.cache
def _libvirt_connection():
    conn = libvirt.open()
    return conn


def _get_dhcp_leases_for_connection(uri) -> list[DhcpLeaseInfo]:
    try:
        conn = libvirt.open(uri)
    except libvirtError:
        return []

    dhcp_leases = []
    for network in conn.listAllNetworks():
        for dhcp_lease_data in network.DHCPLeases():
            parsed_time = datetime.fromtimestamp(dhcp_lease_data.get("expirytime", 0))
            lease_info = DhcpLeaseInfo(
                mac=dhcp_lease_data.get("mac", ""),
                interface=dhcp_lease_data.get("iface", ""),
                client_id=dhcp_lease_data.get("clientid", ""),
                expiry_time=parsed_time,
                ip_address=dhcp_lease_data.get("ipaddr", ""),
                prefix=dhcp_lease_data.get("prefix", 0),
                hostname=dhcp_lease_data.get("hostname"),
            )
            dhcp_leases.append(lease_info)
    return dhcp_leases


@functools.cache
def _get_dhcp_leases() -> list[DhcpLeaseInfo]:
    # we can't reuse _libvirt_connection(), because it's common for session vms to use bridge
    # created by default system network
    all_leases = itertools.chain.from_iterable(
        _get_dhcp_leases_for_connection(uri) for uri in LIBVIRT_CONNECTION_URIS
    )
    return list(all_leases)


def _get_domain_ip_address_guestinfo(guest_info) -> str | None:
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


def _domain_has_guest_agent(domain_tree: ET.Element) -> bool:
    for channel in domain_tree.findall(".//devices/channel"):
        target = channel.find("./target")
        if target is None:
            continue
        if not target.get("name", "").startswith("org.qemu.guest_agent"):
            continue
        conn_state = target.get("state", "disconnected")
        if conn_state == "connected":
            return True
    return False


def _try_get_domain_guest_data(
    domain_tree: ET.Element, domain: libvirt.virDomain
) -> dict[str, str]:
    if not _domain_has_guest_agent(domain_tree):
        return {}

    try:
        guest_info = domain.guestInfo()
    except libvirtError:
        return {}

    return {
        "ip_address": _get_domain_ip_address_guestinfo(guest_info),
        "os_id": guest_info.get("os.id"),
        "os_version_id": guest_info.get("os.version-id"),
    }


def _get_domain_xml_os_ids(domain_tree: ET.Element) -> tuple[str, str]:
    default_tuple = ("", "")
    os_elem = domain_tree.find(".//libosinfo:os", LIBVIRT_XML_NAMESPACES)
    if os_elem is None:
        return default_tuple

    osinfo_uri = os_elem.get("id")
    if not osinfo_uri:
        return default_tuple

    # the correct way is to consult osinfo DB, but that works for all common cases
    parsed = urlparse(osinfo_uri)
    os_id, _, os_version = parsed.path.strip("/").partition("/")
    return (os_id, os_version)


def _get_domain_mac_addresses(domain_tree: ET.Element) -> list[str]:
    macs = []
    for mac_elem in domain_tree.findall(".//interface/mac"):
        address = mac_elem.get("address")
        if not address:
            continue
        macs.append(address)
    return macs


def _get_domain_ip_address_leases(
    mac_addresses: list[str], dhcp_leases: list[DhcpLeaseInfo]
) -> list[str]:
    ip_addresses = []
    haystack = set(mac_addresses)
    for lease_info in dhcp_leases:
        if lease_info.mac not in haystack:
            continue
        ip_addresses.append(lease_info.ip_address)
    return ip_addresses


def _get_domain_supplementary_data(domain: libvirt.virDomain) -> dict[str, str]:
    domain_tree = ET.fromstring(domain.XMLDesc())

    if data := _try_get_domain_guest_data(domain_tree, domain):
        return data

    os_id, os_version_id = _get_domain_xml_os_ids(domain_tree)
    dhcp_leases = _get_dhcp_leases()
    mac_addresses = _get_domain_mac_addresses(domain_tree)
    ip_addresses = _get_domain_ip_address_leases(mac_addresses, dhcp_leases)

    data = {}
    if os_id:
        data["os_id"] = os_id
    if os_version_id:
        data["os_version_id"] = os_version_id
    try:
        data["ip_address"] = ip_addresses[0]
    except IndexError:
        pass

    return data


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
        supplementary_data = _get_domain_supplementary_data(domain)
        disks = _get_domain_disks(domain_data)
        domain_obj = DomainInfo(
            name=domain.name(),
            UUID=domain.UUIDString(),
            state=DomainStateEnum(domain_data.get("state.state", 0)),
            disks=disks,
            ip_address=supplementary_data.get("ip_address"),
            os_id=supplementary_data.get("os_id"),
            os_version_id=supplementary_data.get("os_version_id"),
        )
        domains.append(domain_obj)
    return domains


def _get_pool_path(xml: str) -> Path:
    tree = ET.fromstring(xml)
    for path_node in tree.findall(".//path"):
        if path_value := path_node.text:
            return Path(path_value)
    raise VmmgrException("<path> element not found")


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
