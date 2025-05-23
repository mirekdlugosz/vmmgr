import unittest
from pathlib import Path

from libvirt import libvirtError

from vmmgr.libvirt import _get_domain_disks
from vmmgr.libvirt import _get_domain_ip_address
from vmmgr.libvirt import _get_pool_path
from vmmgr.os import _get_vm_name_template
from vmmgr.os import _match_osinfo
from vmmgr.os import _parse_virt_inspector_output
from vmmgr.types import VirtInspectorData


class ScriptTests(unittest.TestCase):
    def setUp(self):
        self._known_osinfo = [
            "fedora41",
            "fedora42",
            "fedora-unknown",
            "rhel8.10",
            "rhel9.4",
            "rhel9-unknown",
            "ubuntu25.04",
        ]

    def test_xml_path_exists(self):
        xml = """<pool type='dir'><target><path>/tmp/mypath</path></target></pool>"""
        p = _get_pool_path(xml)
        self.assertEqual(p, Path("/tmp/mypath"))

    def test_xml_path_error(self):
        xml = """<pool type='dir'><name>mypool</name></pool>"""
        with self.assertRaises(libvirtError):
            p = _get_pool_path(xml)

    def test_ip_addr_no_if(self):
        guest_info = {"noif": "key"}
        ip_addr = _get_domain_ip_address(guest_info)
        self.assertEqual(ip_addr, None)

    def test_ip_addr_only_lo(self):
        guest_info = {
            "if.0.addr.0.addr": "127.0.0.1",
            "if.0.addr.0.type": "ipv4",
            "if.0.name": "lo"
        }
        ip_addr = _get_domain_ip_address(guest_info)
        self.assertEqual(ip_addr, None)

    def test_ip_addr_only_ipv6(self):
        guest_info = {
            "if.0.addr.0.addr": "::1",
            "if.0.addr.0.type": "ipv6",
            "if.0.name": "lo",
            "if.1.addr.0.addr": "fe80::32aa:6994:4e0b:d439",
            "if.1.addr.0.type": "ipv6",
            "if.1.name": "eth0",
        }
        ip_addr = _get_domain_ip_address(guest_info)
        self.assertEqual(ip_addr, "fe80::32aa:6994:4e0b:d439")

    def test_ip_addr_only_ipv4(self):
        guest_info = {
            "if.0.addr.0.addr": "127.0.0.1",
            "if.0.addr.0.type": "ipv4",
            "if.0.name": "lo",
            "if.1.addr.0.addr": "192.168.122.225",
            "if.1.addr.0.type": "ipv4",
            "if.1.name": "eth0",
        }
        ip_addr = _get_domain_ip_address(guest_info)
        self.assertEqual(ip_addr, "192.168.122.225")

    def test_ip_addr_prefer_ipv4(self):
        guest_info = {
            "if.0.addr.0.addr": "127.0.0.1",
            "if.0.addr.0.type": "ipv4",
            "if.0.addr.1.addr": "::1",
            "if.0.addr.1.type": "ipv6",
            "if.0.name": "lo",
            "if.1.addr.0.addr": "192.168.122.225",
            "if.1.addr.0.type": "ipv4",
            "if.1.addr.1.addr": "fe80::32aa:6994:4e0b:d439",
            "if.1.addr.1.type": "ipv6",
            "if.1.name": "eth0",
        }
        ip_addr = _get_domain_ip_address(guest_info)
        self.assertEqual(ip_addr, "192.168.122.225")

    def test_domain_no_disks(self):
        domain_data = {'vcpu.current': 2}
        disks = _get_domain_disks(domain_data)
        expected = []
        self.assertEqual(disks, expected)

    def test_domain_disk_count(self):
        domain_data = {'block.count': 2}
        disks = _get_domain_disks(domain_data)
        expected = []
        self.assertEqual(disks, expected)

    def test_domain_one_disk(self):
        domain_data = {
            "block.0.path": "/tmp/myimg.qcow2"
        }
        disks = _get_domain_disks(domain_data)
        expected = [Path("/tmp/myimg.qcow2")]
        self.assertEqual(disks, expected)

    def test_domain_two_disks(self):
        domain_data = {
            "block.0.path": "/tmp/myimg.qcow2",
            "block.1.path": "/tmp/otherimg.qcow2"
        }
        disks = _get_domain_disks(domain_data)
        expected = [Path("/tmp/myimg.qcow2"), Path("/tmp/otherimg.qcow2")]
        self.assertEqual(disks, expected)

    def test_domain_two_disks_mix(self):
        domain_data = {
            "block.0.path": "/tmp/myimg.qcow2",
            "block.1.name": "hdb"
        }
        disks = _get_domain_disks(domain_data)
        expected = [Path("/tmp/myimg.qcow2")]
        self.assertEqual(disks, expected)

    def test_vm_name_boundary(self):
        source = "fedora-41-x86_64-kvm.qcow2"
        pattern = "fedora-41"
        vm_name = _get_vm_name_template(source, pattern)
        self.assertEqual(vm_name, "fedora-41")

    def test_vm_name_middle(self):
        source = "rhel-8.10-x86_64-kvm.qcow2"
        pattern = "rhel-8"
        vm_name = _get_vm_name_template(source, pattern)
        self.assertEqual(vm_name, "rhel-8.10")

    def test_vm_name_no_dash(self):
        source = "ubuntu24.04.qcow2"
        pattern = "ubuntu"
        vm_name = _get_vm_name_template(source, pattern)
        self.assertEqual(vm_name, "ubuntu24.04")

    def test_parse_virt_inspector_no_os(self):
        xml = "<operatingsystems/>"
        obj = _parse_virt_inspector_output(xml)
        self.assertEqual(obj, None)

    def test_parse_virt_inspector_name(self):
        xml = (
            "<operatingsystems><operatingsystem>"
            "<name>linux</name>"
            "</operatingsystem></operatingsystems>"
        )
        expected = VirtInspectorData(name="linux")
        obj = _parse_virt_inspector_output(xml)
        self.assertEqual(obj, expected)

    def test_parse_virt_inspector_distro(self):
        xml = (
            "<operatingsystems><operatingsystem>"
            "<distro>fake</distro>"
            "</operatingsystem></operatingsystems>"
        )
        expected = VirtInspectorData(distro="fake")
        obj = _parse_virt_inspector_output(xml)
        self.assertEqual(obj, expected)

    def test_parse_virt_inspector_major_version(self):
        xml = (
            "<operatingsystems><operatingsystem>"
            "<major_version>0</major_version>"
            "</operatingsystem></operatingsystems>"
        )
        expected = VirtInspectorData(major_version="0")
        obj = _parse_virt_inspector_output(xml)
        self.assertEqual(obj, expected)

    def test_parse_virt_inspector_minor_version(self):
        xml = (
            "<operatingsystems><operatingsystem>"
            "<minor_version>0</minor_version>"
            "</operatingsystem></operatingsystems>"
        )
        expected = VirtInspectorData(minor_version="0")
        obj = _parse_virt_inspector_output(xml)
        self.assertEqual(obj, expected)

    def test_parse_virt_inspector_osinfo(self):
        xml = (
            "<operatingsystems><operatingsystem>"
            "<osinfo>fake0</osinfo>"
            "</operatingsystem></operatingsystems>"
        )
        expected = VirtInspectorData(osinfo="fake0")
        obj = _parse_virt_inspector_output(xml)
        self.assertEqual(obj, expected)

    def test_parse_virt_inspector_fedora42(self):
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
        self.assertEqual(obj, expected)

    def test_parse_virt_inspector_rhel10(self):
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
        self.assertEqual(obj, expected)

    def test_parse_virt_inspector_ubuntu25(self):
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
        self.assertEqual(obj, expected)

    def test_match_osinfo_inspector(self):
        virt_inspector_data = VirtInspectorData(
            osinfo="fedora42",
        )
        osinfo = _match_osinfo(self._known_osinfo, virt_inspector_data, "")
        self.assertEqual(osinfo, "fedora42")

    def test_match_osinfo_inspector_majorminor(self):
        virt_inspector_data = VirtInspectorData(
            distro="rhel",
            major_version="8",
            minor_version="10",
        )
        osinfo = _match_osinfo(self._known_osinfo, virt_inspector_data, "")
        self.assertEqual(osinfo, "rhel8.10")

    def test_match_osinfo_inspector_major(self):
        virt_inspector_data = VirtInspectorData(
            distro="fedora",
            major_version="41",
            minor_version="0",
        )
        osinfo = _match_osinfo(self._known_osinfo, virt_inspector_data, "")
        self.assertEqual(osinfo, "fedora41")

    def test_match_osinfo_inspector_major_unknown(self):
        virt_inspector_data = VirtInspectorData(
            distro="rhel",
            major_version="9",
            minor_version="12",
        )
        osinfo = _match_osinfo(self._known_osinfo, virt_inspector_data, "")
        self.assertEqual(osinfo, "rhel9-unknown")

    def test_match_osinfo_inspector_distro(self):
        virt_inspector_data = VirtInspectorData(
            distro="fedora",
            major_version="43",
            minor_version="0",
        )
        osinfo = _match_osinfo(self._known_osinfo, virt_inspector_data, "")
        self.assertEqual(osinfo, "fedora-unknown")

    def test_match_osinfo_inspector_linux(self):
        virt_inspector_data = VirtInspectorData(
            name="linux"
        )
        osinfo = _match_osinfo(self._known_osinfo, virt_inspector_data, "")
        self.assertEqual(osinfo, "linux2024")

    def test_match_osinfo_filename_rhel(self):
        virt_inspector_data = VirtInspectorData()
        file_name = "rhel-9.4-x86_64-kvm.qcow2"
        osinfo = _match_osinfo(self._known_osinfo, virt_inspector_data, file_name)
        self.assertEqual(osinfo, "rhel9.4")

    def test_match_osinfo_filename_fedora(self):
        virt_inspector_data = VirtInspectorData()
        file_name = "fedora-41-x86_64-kvm.qcow2"
        osinfo = _match_osinfo(self._known_osinfo, virt_inspector_data, file_name)
        self.assertEqual(osinfo, "fedora41")

    def test_match_osinfo_filename_fedora_unknown(self):
        virt_inspector_data = VirtInspectorData()
        file_name = "fedora-latest-x86_64-kvm.qcow2"
        osinfo = _match_osinfo(self._known_osinfo, virt_inspector_data, file_name)
        self.assertEqual(osinfo, "fedora-unknown")

    def test_match_osinfo_filename_ubuntu(self):
        virt_inspector_data = VirtInspectorData()
        file_name = "ubuntu25.04.qcow2"
        osinfo = _match_osinfo(self._known_osinfo, virt_inspector_data, file_name)
        self.assertEqual(osinfo, "ubuntu25.04")

    def test_match_osinfo_fallback(self):
        osinfo = _match_osinfo(self._known_osinfo, VirtInspectorData(), "")
        self.assertEqual(osinfo, "unknown")
