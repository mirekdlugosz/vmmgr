from vmmgr.os import _get_vm_name_template
from vmmgr.os import _match_osinfo
from vmmgr.os import _parse_virt_inspector_output
from vmmgr.types import VirtInspectorData


KNOWN_OSINFO = [
    "fedora41",
    "fedora42",
    "fedora-unknown",
    "rhel8.10",
    "rhel9.4",
    "rhel9-unknown",
    "ubuntu25.04",
]


def test_vm_name_boundary():
    source = "fedora-41-x86_64-kvm.qcow2"
    pattern = "fedora-41"
    vm_name = _get_vm_name_template(source, pattern)
    assert vm_name == "fedora-41"


def test_vm_name_middle():
    source = "rhel-8.10-x86_64-kvm.qcow2"
    pattern = "rhel-8"
    vm_name = _get_vm_name_template(source, pattern)
    assert vm_name == "rhel-8.10"


def test_vm_name_no_dash():
    source = "ubuntu24.04.qcow2"
    pattern = "ubuntu"
    vm_name = _get_vm_name_template(source, pattern)
    assert vm_name == "ubuntu24.04"


def test_parse_virt_inspector_no_os():
    xml = "<operatingsystems/>"
    obj = _parse_virt_inspector_output(xml)
    assert obj == None


def test_parse_virt_inspector_name():
    xml = (
        "<operatingsystems><operatingsystem><name>linux</name></operatingsystem></operatingsystems>"
    )
    expected = VirtInspectorData(name="linux")
    obj = _parse_virt_inspector_output(xml)
    assert obj == expected


def test_parse_virt_inspector_distro():
    xml = (
        "<operatingsystems><operatingsystem>"
        "<distro>fake</distro>"
        "</operatingsystem></operatingsystems>"
    )
    expected = VirtInspectorData(distro="fake")
    obj = _parse_virt_inspector_output(xml)
    assert obj == expected


def test_parse_virt_inspector_major_version():
    xml = (
        "<operatingsystems><operatingsystem>"
        "<major_version>0</major_version>"
        "</operatingsystem></operatingsystems>"
    )
    expected = VirtInspectorData(major_version="0")
    obj = _parse_virt_inspector_output(xml)
    assert obj == expected


def test_parse_virt_inspector_minor_version():
    xml = (
        "<operatingsystems><operatingsystem>"
        "<minor_version>0</minor_version>"
        "</operatingsystem></operatingsystems>"
    )
    expected = VirtInspectorData(minor_version="0")
    obj = _parse_virt_inspector_output(xml)
    assert obj == expected


def test_parse_virt_inspector_osinfo():
    xml = (
        "<operatingsystems><operatingsystem>"
        "<osinfo>fake0</osinfo>"
        "</operatingsystem></operatingsystems>"
    )
    expected = VirtInspectorData(osinfo="fake0")
    obj = _parse_virt_inspector_output(xml)
    assert obj == expected


def test_parse_virt_inspector_fedora42():
    xml = (
        "<operatingsystems><operatingsystem>"
        "<name>linux</name>"
        "<distro>fedora</distro>"
        "<major_version>42</major_version>"
        "<minor_version>0</minor_version>"
        "<osinfo>fedora42</osinfo>"
        "</operatingsystem></operatingsystems>"
    )
    expected = VirtInspectorData(
        osinfo="fedora42",
        distro="fedora",
        major_version="42",
        minor_version="0",
        name="linux",
    )
    obj = _parse_virt_inspector_output(xml)
    assert obj == expected


def test_parse_virt_inspector_rhel10():
    xml = (
        "<operatingsystems><operatingsystem>"
        "<name>linux</name>"
        "<distro>rhel</distro>"
        "<major_version>10</major_version>"
        "<minor_version>2</minor_version>"
        "<osinfo>rhel10.2</osinfo>"
        "</operatingsystem></operatingsystems>"
    )
    expected = VirtInspectorData(
        osinfo="rhel10.2",
        distro="rhel",
        major_version="10",
        minor_version="2",
        name="linux",
    )
    obj = _parse_virt_inspector_output(xml)
    assert obj == expected


def test_parse_virt_inspector_ubuntu25():
    xml = (
        "<operatingsystems><operatingsystem>"
        "<name>linux</name>"
        "<distro>ubuntu</distro>"
        "<major_version>25</major_version>"
        "<minor_version>4</minor_version>"
        "<osinfo>ubuntu25.04</osinfo>"
        "</operatingsystem></operatingsystems>"
    )
    expected = VirtInspectorData(
        osinfo="ubuntu25.04",
        distro="ubuntu",
        major_version="25",
        minor_version="4",
        name="linux",
    )
    obj = _parse_virt_inspector_output(xml)
    assert obj == expected


def test_match_osinfo_inspector():
    virt_inspector_data = VirtInspectorData(
        osinfo="fedora42",
    )
    osinfo = _match_osinfo(KNOWN_OSINFO, virt_inspector_data, "")
    assert osinfo == "fedora42"


def test_match_osinfo_inspector_majorminor():
    virt_inspector_data = VirtInspectorData(
        distro="rhel",
        major_version="8",
        minor_version="10",
    )
    osinfo = _match_osinfo(KNOWN_OSINFO, virt_inspector_data, "")
    assert osinfo == "rhel8.10"


def test_match_osinfo_inspector_major():
    virt_inspector_data = VirtInspectorData(
        distro="fedora",
        major_version="41",
        minor_version="0",
    )
    osinfo = _match_osinfo(KNOWN_OSINFO, virt_inspector_data, "")
    assert osinfo == "fedora41"


def test_match_osinfo_inspector_major_unknown():
    virt_inspector_data = VirtInspectorData(
        distro="rhel",
        major_version="9",
        minor_version="12",
    )
    osinfo = _match_osinfo(KNOWN_OSINFO, virt_inspector_data, "")
    assert osinfo == "rhel9-unknown"


def test_match_osinfo_inspector_distro():
    virt_inspector_data = VirtInspectorData(
        distro="fedora",
        major_version="43",
        minor_version="0",
    )
    osinfo = _match_osinfo(KNOWN_OSINFO, virt_inspector_data, "")
    assert osinfo == "fedora-unknown"


def test_match_osinfo_inspector_linux():
    virt_inspector_data = VirtInspectorData(name="linux")
    osinfo = _match_osinfo(KNOWN_OSINFO, virt_inspector_data, "")
    assert osinfo == "linux2024"


def test_match_osinfo_filename_rhel():
    virt_inspector_data = VirtInspectorData()
    file_name = "rhel-9.4-x86_64-kvm.qcow2"
    osinfo = _match_osinfo(KNOWN_OSINFO, virt_inspector_data, file_name)
    assert osinfo == "rhel9.4"


def test_match_osinfo_filename_fedora():
    virt_inspector_data = VirtInspectorData()
    file_name = "fedora-41-x86_64-kvm.qcow2"
    osinfo = _match_osinfo(KNOWN_OSINFO, virt_inspector_data, file_name)
    assert osinfo == "fedora41"


def test_match_osinfo_filename_fedora_unknown():
    virt_inspector_data = VirtInspectorData()
    file_name = "fedora-latest-x86_64-kvm.qcow2"
    osinfo = _match_osinfo(KNOWN_OSINFO, virt_inspector_data, file_name)
    assert osinfo == "fedora-unknown"


def test_match_osinfo_filename_ubuntu():
    virt_inspector_data = VirtInspectorData()
    file_name = "ubuntu25.04.qcow2"
    osinfo = _match_osinfo(KNOWN_OSINFO, virt_inspector_data, file_name)
    assert osinfo == "ubuntu25.04"


def test_match_osinfo_fallback():
    osinfo = _match_osinfo(KNOWN_OSINFO, VirtInspectorData(), "")
    assert osinfo == "unknown"
