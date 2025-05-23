from vmmgr.os import determine_vm_user
from vmmgr.os import get_ssh_private_key
from vmmgr.types import DomainInfo
from vmmgr.types import DomainStateEnum


def table_formatter(vms: list[DomainInfo]) -> str:
    output = []
    header = f"{'NAME':<30} {'STATE':<15} {'IP ADDRESS':<28} {'USER':<10}"
    output.append(header)
    output.append("-" * len(header))
    for vm in vms:
        name = vm.name
        state = vm.state.name
        ip = vm.ip_address or ""
        user = determine_vm_user(vm)
        output.append(f"{name:<30} {state:<15} {ip:<28} {user:<10}")
    return "\n".join(output)


def shell_formatter(vms: list[DomainInfo]) -> str:
    output = []
    for vm in vms:
        name = vm.name
        ip = vm.ip_address
        state = vm.state.name
        user = determine_vm_user(vm)
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
        user = determine_vm_user(vm)
        comment = "" if vm.state == DomainStateEnum.RUNNING else "# "
        line = (
            f"{comment}{name} ansible_host={ip} "
            f"ansible_ssh_private_key_file={ssh_key} ansible_user={user}"
        )
        output.append(line)
    return "\n".join(output)
