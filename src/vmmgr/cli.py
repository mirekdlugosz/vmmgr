import sys
import argparse
from pathlib import Path

from vmmgr.constants import XDG_RUNTIME_DIR
from vmmgr.formatters import ansible_formatter
from vmmgr.formatters import shell_formatter
from vmmgr.formatters import table_formatter
from vmmgr.types import DomainStateEnum
from vmmgr.os import execute_cmd
from vmmgr.os import get_cloud_init_content
from vmmgr.os import get_new_vm_name
from vmmgr.os import get_osinfo_value
from vmmgr.libvirt import get_template_volumes
from vmmgr.libvirt import get_vmmgr_managed_vms
from vmmgr.libvirt import get_vmmgr_pool


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
