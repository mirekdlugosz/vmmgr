#!/usr/bin/python3

import itertools
import functools
import os
import sys
import subprocess
import argparse
from operator import itemgetter
from typing import Any
import unittest
from pathlib import Path
from dataclasses import dataclass
from enum import Enum
from xml.dom import minidom

import libvirt
from libvirt import libvirtError

VMMGR_POOL_NAME = os.getenv("VMMGR_POOL", "vmmgr")
VMMGR_TEMPLATE_IMAGES_POOLS = os.getenv("VMMGR_TEMPLATE_IMAGES_POOLS", "default")
XDG_RUNTIME_DIR = os.getenv("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
IMAGE_EXTENSIONS = ("qcow2", "img")


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
    name: str| None = None


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
        "os_version_id": guest_info.get("os.version-id")
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
        sys.exit(f"libvirt pool '{VMMGR_POOL_NAME}' not found. Did you change VMMGR_POOL environment variable?")
    return vmmgr_pool


def get_vmmgr_managed_vms():
    vmmgr_pool = get_vmmgr_pool()
    vmmgr_volumes = set([Path(v.path()) for v in vmmgr_pool.volumes])
    vms = get_domains_info()
    filtered = [vm for vm in vms if set(vm.disks).intersection(vmmgr_volumes)]
    return filtered


def _get_vm_name_template(source_name: str, user_pattern: str) -> str:
    try:
        end = source_name.index("-", len(user_pattern))
        return source_name[:end]
    except ValueError:
        return Path(source_name).stem


def get_new_vm_name(source_image_path: str, user_pattern: str) -> str:
    known_vms = set([vm.name for vm in get_vmmgr_managed_vms()])
    source_name = Path(source_image_path).name
    name_template = _get_vm_name_template(source_name, user_pattern)

    for num in itertools.count(start=1, step=1):
        new_name = f"{name_template}-{num}"
        if new_name not in known_vms:
            return new_name


def get_cloud_init_content(candidates: tuple[str | Path | None, ...]) -> str:
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate)
        if path.is_dir():
            path = path / "cloud-init" / "user-data"
        try:
            return path.read_text()
        except OSError:
            continue
    content = [
        "#cloud-config",
        "allow_public_ssh_keys: true",
    ]
    return "\n".join(content)


def execute_cmd(cmd: list[str], dry_run: bool):
    print(" ".join(cmd))
    if dry_run:
        return
    res = subprocess.run(cmd)
    if res.returncode == 0:
        return res
    sys.exit(res.returncode)


def _get_known_os_info(dry_run: bool) -> list[str]:
    if dry_run:
        return ["linux2024"]

    os_query_cmd = [
        "osinfo-query",
        "os",
        "-f",
        "short-id",
    ]
    res = subprocess.run(os_query_cmd, capture_output=True, text=True)
    known_os = [
        os_name.strip() for os_name
        in res.stdout.split("\n")[2:]
    ]
    return [os for os in known_os if os]


def _parse_virt_inspector_output(xml: str) -> VirtInspectorData | None:
    requested_keys = ("osinfo", "distro", "major_version", "minor_version", "name")
    inspected_data = {}
    tree = minidom.parseString(xml)
    for os_elem in tree.getElementsByTagName("operatingsystem"):
        for child in os_elem.childNodes:
            if child.nodeType != child.ELEMENT_NODE:
                continue
            key = child.nodeName
            if child.nodeName not in requested_keys:
                continue
            for content in child.childNodes:
                if content.nodeType == content.TEXT_NODE:
                    inspected_data[key] = content.nodeValue
                    break
        return VirtInspectorData(**inspected_data)
    return None


def _get_virt_inspector_data(template_image_path: str, dry_run: bool) -> VirtInspectorData | None:
    if dry_run:
        return None
    virt_inspector_cmd = [
        "virt-inspector",
        "-a", template_image_path,
    ]
    print(" ".join(virt_inspector_cmd))
    res = subprocess.run(virt_inspector_cmd, capture_output=True, text=True)
    if res.returncode != 0:
        return None
    return _parse_virt_inspector_output(res.stdout)


def _match_osinfo(known_osinfo: list[str], virt_inspector_data: VirtInspectorData | None, file_name: str) -> str:
    if virt_inspector_data:
        if (osinfo := virt_inspector_data.osinfo) and osinfo in known_osinfo:
            return osinfo
        if (distro := virt_inspector_data.distro):
            major_version = virt_inspector_data.major_version
            minor_version = virt_inspector_data.minor_version
            candidates = [
                f"{distro}{major_version}.{minor_version}",
                f"{distro}{major_version}",
                f"{distro}{major_version}-unknown",
                f"{distro}",
                f"{distro}-unknown",
            ]
            for candidate in candidates:
                if candidate in known_osinfo:
                    return candidate

    while file_name:
        transformed_file_name = file_name.replace("-", "")
        candidates = [file_name, f"{file_name}-unknown", transformed_file_name, f"{transformed_file_name}-unknown"]
        for candidate in candidates:
            candidate = candidate.lower()
            if candidate in known_osinfo:
                return candidate
        file_name = file_name[:-1]

    if virt_inspector_data and virt_inspector_data.name == "linux":
        return "linux2024"

    return "unknown"


def get_osinfo_value(template_image_path: str, dry_run: bool) -> str:
    # FIXME: cache w pliku? implementacja jako dekorator?
    known_osinfo = _get_known_os_info(dry_run)
    virt_inspector_data = _get_virt_inspector_data(template_image_path, dry_run)
    file_name = Path(template_image_path).name
    
    matching_os = _match_osinfo(known_osinfo, virt_inspector_data, file_name)
    return matching_os


# --- Command: create --- #
def handle_create(args):
    template_pool_map = get_template_volumes()
    short_full_map = {str(Path(vol).name): vol for vol in template_pool_map.keys()}
    if len(short_full_map) != len(template_pool_map):
        sys.exit("Multiple pools contain files with the same name. Results would be unpredictable")

    matching_templates = list(short_full_map.keys())
    if pattern := args.pattern:
        matching_templates = [
            template for template in matching_templates
            if template.startswith(pattern)
        ]

    if args.list:
        print("Available VM template images:")
        for template in sorted(matching_templates):
            print(f" {template}")
        return

    if not matching_templates:
        sys.exit("No VM template images matching the pattern")

    if len(matching_templates) > 1:
        sys.exit("Ambiguous pattern. Results would be unpredictable")

    template_image_path = short_full_map.get(matching_templates[0])
    template_pool = template_pool_map.get(template_image_path)
    vmmgr_pool = get_vmmgr_pool()

    new_vm_name = get_new_vm_name(template_image_path, pattern)
    new_vm_image_path = (vmmgr_pool.path / f"{new_vm_name}.qcow2").resolve()

    user_data_path = Path(XDG_RUNTIME_DIR) / f"vmmgr-{new_vm_name}-user-data"
    meta_data_path = Path(XDG_RUNTIME_DIR) / f"vmmgr-{new_vm_name}-meta-data"
    cloud_init_candidates = (args.cloud_init, template_pool.path, vmmgr_pool.path)
    user_data_path.write_text(get_cloud_init_content(cloud_init_candidates))
    meta_data_path.write_text(f"local-hostname: '{new_vm_name}'\n")

    qemu_img_cmd = [
        "qemu-img", "create", "-f", "qcow2",
        "-b", template_image_path, "-F", "qcow2",
        new_vm_image_path.as_posix()
    ]
    if args.disk_size:
        qemu_img_cmd.append(args.disk_size)
    execute_cmd(qemu_img_cmd, args.dry_run)

    virt_install_cmd = [
        "virt-install",
        "--name", new_vm_name,
        "--memory", "2048",
        "--vcpus", "2",
        "--disk", new_vm_image_path.as_posix(),
        "--import",
        "--network", "bridge=virbr0",
        "--cloud-init", f"user-data={user_data_path.as_posix()},meta-data={meta_data_path.as_posix()}",
        "--noautoconsole",
    ]
    if args.extra_args:
        virt_install_cmd.extend(args.extra_args)
    if not any(flag in virt_install_cmd for flag in ("--osinfo", "--os-variant")):
        os_info = get_osinfo_value(template_image_path, args.dry_run)
        virt_install_cmd.extend(("--osinfo", os_info))
    execute_cmd(virt_install_cmd, args.dry_run)


def handle_delete(args):
    vmmgr_pool = get_vmmgr_pool()
    managed_vms = {vm.name: vm for vm in get_vmmgr_managed_vms()}
    selected_vms = args.vm_name
    if args.all:
        selected_vms = managed_vms.keys()

    for vm_name in selected_vms:
        vm = managed_vms.get(vm_name)
        if not vm:
            continue

        remove_cmd = [
            "virsh",
            "destroy",
            "--remove-logs",
            "--domain", vm_name,
        ]
        if vm.state == DomainStateEnum.RUNNING:
            execute_cmd(remove_cmd, args.dry_run)

        disks = [
            path.as_posix() for path
            in vm.disks
            if path.is_relative_to(vmmgr_pool.path)
        ]

        undefine_cmd = [
            "virsh",
            "undefine",
            "--managed-save",
            "--storage", ",".join(disks),
            "--domain", vm_name,
        ]
        execute_cmd(undefine_cmd, args.dry_run)


# FIXME: te dziwne komentarze?
# --- Commands: list, export --- #
# FIXME: przepisz funkcję
def determine_vm_user(vm_name):
    """
    Decide which user to use when connecting based on the VM name.
      • If the VM name starts with template "dsc-", then use "dscci".
      • Otherwise, if it starts with "fedora" use "fedora",
      • if it starts with "rhel" use "cloud-user".
      • If none of these match, return the empty string.
    """
    parts = vm_name.split('-')
    if parts[0] == "dsc":
        return "dscci"
    if parts[0].lower() == "fedora":
        return "fedora"
    if parts[0].lower() == "rhel":
        return "cloud-user"
    return ""


def get_ssh_private_key() -> str:
    key_names = ("id_ecdsa", "id_ecdsa_sk", "id_ed25519", "id_ed25519_sk", "id_rsa")
    for candidate in key_names:
        path = Path.home() / ".ssh" / candidate
        if path.exists():
            return path.as_posix()
    return "NO_KEY"


def table_formatter(vms: list[DomainInfo]) -> str:
    output = []
    header = f"{'NAME':<30} {'STATE':<15} {'IP ADDRESS':<28} {'USER':<10}"
    output.append(header)
    output.append("-" * len(header))
    for vm in vms:
        name = vm.name
        state = vm.state.name
        ip = vm.ip_address or ""
        user = determine_vm_user(name)
        output.append(f"{name:<30} {state:<15} {ip:<28} {user:<10}")
    return "\n".join(output)


def shell_formatter(vms: list[DomainInfo]) -> str:
    output = []
    for vm in vms:
        name = vm.name
        ip = vm.ip_address
        state = vm.state.name
        user = determine_vm_user(name)
        output.append(f"VM_NAME={name}    # {state}")
        output.append(f"VM_USER={user}")
        output.append(f"IP_ADDR={ip}")
        output.append("")
    return "\n".join(output)


def ansible_formatter(vms: list[DomainInfo]) -> str:
    output = []
    ssh_key = get_ssh_private_key()

    for vm in vms:
        name = vm.name
        ip = vm.ip_address
        user = determine_vm_user(name)
        comment = "" if vm.state == DomainStateEnum.RUNNING else "# "
        output.append(f"{comment}{name} ansible_host={ip} ansible_ssh_private_key_file={ssh_key} ansible_user={user}")
    return "\n".join(output)


def handle_list(args):
    vms = get_vmmgr_managed_vms()
    formatter = table_formatter
    if args.format == "shell":
        formatter = shell_formatter
    elif args.format == "ansible":
        formatter = ansible_formatter

    print(formatter(vms))


# --- Main argument parser --- #
def main():
    parser = argparse.ArgumentParser(description="Virtual Machine Manager (vmmgr)")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create_parser = subparsers.add_parser("create", help="Create a new virtual machine")
    create_parser.add_argument("pattern", nargs="?",
                               help="Base OS image name")
    create_parser.add_argument("--list", action="store_true",
                               help="List available base OS images for creation (does not create a VM)")
    create_parser.add_argument("-n", "--dry-run", action="store_true",
                               help="Don't run external commands")
    create_parser.add_argument("--disk-size", help="Optional disk size appended to qemu-img command")
    create_parser.add_argument("--cloud-init", help="Path to cloud-init user-data file to copy")
    create_parser.add_argument("extra_args", nargs=argparse.REMAINDER,
                               help="Additional arguments passed to virt-install")

    delete_parser = subparsers.add_parser("delete", help="Delete a virtual machine")
    delete_parser.add_argument("-n", "--dry-run", action="store_true",
                               help="Don't run external commands")
    delete_parser.add_argument("--all", action="store_true",
                               help="Delete all virtual machines")
    delete_parser.add_argument("vm_name", nargs="*",
                               help="Virtual machine name")

    list_parser = subparsers.add_parser("list", help="List virtual machines")
    list_parser.add_argument("-f", "--format", choices=["shell", "ansible"],
                             help="Display in format suitable for other tools")

    args = parser.parse_args()
    match args.command:
        case "create":
            handle_create(args)
        case "delete":
            handle_delete(args)
        case "list":
            handle_list(args)


if __name__ == '__main__':
    main()
