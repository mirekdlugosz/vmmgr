import itertools
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Iterable

from vmmgr.constants import SSH_KEY_FILES
from vmmgr.constants import USER_OS_MAP
from vmmgr.constants import USER_TEMPLATE_MAP
from vmmgr.types import DomainInfo
from vmmgr.types import VirtInspectorData


def _get_vm_name_template(source_name: str, user_pattern: str) -> str:
    try:
        end = source_name.index("-", len(user_pattern))
        return source_name[:end]
    except ValueError:
        return Path(source_name).stem


def get_new_vm_name(user_pattern: str, source_image_name: str, known_vms: Iterable[str]) -> str:
    name_template = _get_vm_name_template(source_image_name, user_pattern)

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
    public_ssh_keys = get_ssh_public_keys()
    if public_ssh_keys:
        content.append("ssh_authorized_keys:")
        for public_key in public_ssh_keys:
            key_file_content = public_key.read_text()
            key_file_content = key_file_content.strip()
            content.append(f'  - "{key_file_content}"')
    return "\n".join(content)


# FIXME: extend / remove this
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
    known_os = [os_name.strip() for os_name in res.stdout.split("\n")[2:]]
    return [os for os in known_os if os]


def _parse_virt_inspector_output(xml: str) -> VirtInspectorData | None:
    requested_keys = ("osinfo", "distro", "major_version", "minor_version", "name")
    inspected_data = {}
    tree = ET.fromstring(xml)
    os_elem = tree.find(".//operatingsystem")
    if os_elem is None:
        return None

    for child_node in os_elem.iter():
        key = child_node.tag
        if key not in requested_keys:
            continue
        if path_value := child_node.text:
            inspected_data[key] = path_value

    return VirtInspectorData(**inspected_data)


def _get_virt_inspector_data(template_image_path: str, dry_run: bool) -> VirtInspectorData | None:
    if dry_run:
        return None
    virt_inspector_cmd = [
        "virt-inspector",
        "-a",
        template_image_path,
    ]
    print(" ".join(virt_inspector_cmd))
    res = subprocess.run(virt_inspector_cmd, capture_output=True, text=True)
    if res.returncode != 0:
        return None
    return _parse_virt_inspector_output(res.stdout)


def _match_osinfo(
    known_osinfo: list[str], virt_inspector_data: VirtInspectorData | None, file_name: str
) -> str:
    if virt_inspector_data:
        if (osinfo := virt_inspector_data.osinfo) and osinfo in known_osinfo:
            return osinfo
        if distro := virt_inspector_data.distro:
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
        candidates = [
            file_name,
            f"{file_name}-unknown",
            transformed_file_name,
            f"{transformed_file_name}-unknown",
        ]
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


def determine_vm_user(vm: DomainInfo):
    template, _, _ = vm.name.partition("-")
    if template_user := USER_TEMPLATE_MAP.get(template):
        return template_user

    if os_name := vm.os_id:
        return USER_OS_MAP.get(os_name, "")

    return ""


def get_ssh_public_keys() -> list[Path]:
    found_keys = []
    ssh_key_files = set(f"{fname}.pub" for fname in SSH_KEY_FILES)
    for file in (Path.home() / ".ssh").glob("*.pub"):
        if file.name not in ssh_key_files:
            continue
        found_keys.append(file.resolve())
    return found_keys


def get_ssh_private_key() -> Path | None:
    for candidate in SSH_KEY_FILES:
        path = Path.home() / ".ssh" / candidate
        if path.exists():
            return path
    return None
