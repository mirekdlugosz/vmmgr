import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

import pytest

from vmmgr.libvirt import _domain_has_guest_agent
from vmmgr.libvirt import _get_domain_disks
from vmmgr.libvirt import _get_domain_ip_address_guestinfo
from vmmgr.libvirt import _get_domain_ip_address_leases
from vmmgr.libvirt import _get_domain_mac_addresses
from vmmgr.libvirt import _get_domain_xml_os_ids
from vmmgr.libvirt import _get_pool_path
from vmmgr.types import DhcpLeaseInfo
from vmmgr.types import VmmgrException


def generate_dhcpinfo(mac, ip_address):
    obj = DhcpLeaseInfo(
        mac=mac,
        interface="virbr0",
        client_id="01:25:45:00:00:00:00",
        expiry_time=datetime.fromtimestamp(0),
        ip_address=ip_address,
        prefix=0,
    )
    return obj


def test_domain_no_disks():
    domain_data = {"vcpu.current": 2}
    disks = _get_domain_disks(domain_data)
    expected = []
    assert disks == expected


def test_domain_disk_count():
    domain_data = {"block.count": 2}
    disks = _get_domain_disks(domain_data)
    expected = []
    assert disks == expected


def test_domain_one_disk():
    domain_data = {"block.0.path": "/tmp/myimg.qcow2"}
    disks = _get_domain_disks(domain_data)
    expected = [Path("/tmp/myimg.qcow2")]
    assert disks == expected


def test_domain_two_disks():
    domain_data = {"block.0.path": "/tmp/myimg.qcow2", "block.1.path": "/tmp/otherimg.qcow2"}
    disks = _get_domain_disks(domain_data)
    expected = [Path("/tmp/myimg.qcow2"), Path("/tmp/otherimg.qcow2")]
    assert disks == expected


def test_domain_two_disks_mix():
    domain_data = {"block.0.path": "/tmp/myimg.qcow2", "block.1.name": "hdb"}
    disks = _get_domain_disks(domain_data)
    expected = [Path("/tmp/myimg.qcow2")]
    assert disks == expected


def test_has_guest_agent_rhel_running():
    xml = (
        "<domain><devices>"
        "<channel type='unix'>"
        "<source mode='bind' path='/run/user/1000/libvirt/qemu/run/channel/1-rhel-10.0-1/org.qemu.guest_agent.0'/>"
        "<target type='virtio' name='org.qemu.guest_agent.0' state='connected'/>"
        "<alias name='channel0'/>"
        "<address type='virtio-serial' controller='0' bus='0' port='1'/>"
        "</channel>"
        "</devices></domain>"
    )
    tree = ET.fromstring(xml)
    has_guest_agent = _domain_has_guest_agent(tree)
    assert has_guest_agent == True


def test_has_guest_agent_rhel_shutoff():
    xml = (
        "<domain><devices>"
        "<channel type='unix'>"
        "<target type='virtio' name='org.qemu.guest_agent.0'/>"
        "<address type='virtio-serial' controller='0' bus='0' port='1'/>"
        "</channel>"
        "</devices></domain>"
    )
    tree = ET.fromstring(xml)
    has_guest_agent = _domain_has_guest_agent(tree)
    assert has_guest_agent == False


def test_has_guest_agent_ubuntu_running():
    xml = (
        "<domain><devices>"
        "<channel type='unix'>"
        "<source mode='bind' path='/run/user/1000/libvirt/qemu/run/channel/2-plucky-1/org.qemu.guest_agent.0'/>"
        "<target type='virtio' name='org.qemu.guest_agent.0' state='disconnected'/>"
        "<alias name='channel0'/>"
        "<address type='virtio-serial' controller='0' bus='0' port='1'/>"
        "</channel>"
        "</devices></domain>"
    )
    tree = ET.fromstring(xml)
    has_guest_agent = _domain_has_guest_agent(tree)
    assert has_guest_agent == False


def test_has_guest_agent_ubuntu_shutoff():
    xml = (
        "<domain><devices>"
        "<channel type='unix'>"
        "<target type='virtio' name='org.qemu.guest_agent.0'/>"
        "<address type='virtio-serial' controller='0' bus='0' port='1'/>"
        "</channel>"
        "</devices></domain>"
    )
    tree = ET.fromstring(xml)
    has_guest_agent = _domain_has_guest_agent(tree)
    assert has_guest_agent == False


def test_has_guest_agent_no_info():
    xml = (
        "<domain><devices>"
        "<interface type='bridge'>"
        "<mac address='01:23:45:67:89:ab'/>"
        "<source bridge='virbr0'/>"
        "<model type='virtio'/>"
        "<address type='pci' domain='0x0000' bus='0x01' slot='0x00' function='0x0'/>"
        "</interface>"
        "</devices></domain>"
    )
    tree = ET.fromstring(xml)
    has_guest_agent = _domain_has_guest_agent(tree)
    assert has_guest_agent == False


def test_ip_addr_no_if():
    guest_info = {"noif": "key"}
    ip_addr = _get_domain_ip_address_guestinfo(guest_info)
    assert ip_addr is None


def test_ip_addr_only_lo():
    guest_info = {"if.0.addr.0.addr": "127.0.0.1", "if.0.addr.0.type": "ipv4", "if.0.name": "lo"}
    ip_addr = _get_domain_ip_address_guestinfo(guest_info)
    assert ip_addr is None


def test_ip_addr_only_ipv6():
    guest_info = {
        "if.0.addr.0.addr": "::1",
        "if.0.addr.0.type": "ipv6",
        "if.0.name": "lo",
        "if.1.addr.0.addr": "fe80::32aa:6994:4e0b:d439",
        "if.1.addr.0.type": "ipv6",
        "if.1.name": "eth0",
    }
    ip_addr = _get_domain_ip_address_guestinfo(guest_info)
    assert ip_addr == "fe80::32aa:6994:4e0b:d439"


def test_ip_addr_only_ipv4():
    guest_info = {
        "if.0.addr.0.addr": "127.0.0.1",
        "if.0.addr.0.type": "ipv4",
        "if.0.name": "lo",
        "if.1.addr.0.addr": "192.168.122.225",
        "if.1.addr.0.type": "ipv4",
        "if.1.name": "eth0",
    }
    ip_addr = _get_domain_ip_address_guestinfo(guest_info)
    assert ip_addr == "192.168.122.225"


def test_ip_addr_matching():
    macs = ["01:23:45:67:89:ab", "00:23:45:67:89:00"]
    leases = [
        generate_dhcpinfo(mac="01:23:45:67:89:ab", ip_address="192.168.122.122"),
        generate_dhcpinfo(mac="ba:98:76:54:32:10", ip_address="192.168.122.123"),
    ]
    found = _get_domain_ip_address_leases(macs, leases)
    assert found == ["192.168.122.122"]


def test_ip_addr_many():
    macs = ["01:23:45:67:89:ab", "00:23:45:67:89:00", "ba:98:76:54:32:10"]
    leases = [
        generate_dhcpinfo(mac="01:23:45:67:89:ab", ip_address="192.168.122.122"),
        generate_dhcpinfo(mac="ba:98:76:54:32:10", ip_address="192.168.122.123"),
        generate_dhcpinfo(mac="ab:89:67:45:23:01", ip_address="192.168.122.213"),
        generate_dhcpinfo(mac="10:32:54:76:98:ba", ip_address="192.168.122.221"),
    ]
    found = _get_domain_ip_address_leases(macs, leases)
    assert set(found) == set(["192.168.122.122", "192.168.122.123"])


def test_ip_addr_empty():
    macs = ["ab:01:23:45:67:89", "00:23:45:67:89:00"]
    leases = [
        generate_dhcpinfo(mac="01:23:45:67:89:ab", ip_address="192.168.122.122"),
        generate_dhcpinfo(mac="ba:98:76:54:32:10", ip_address="192.168.122.123"),
        generate_dhcpinfo(mac="ab:89:67:45:23:01", ip_address="192.168.122.213"),
        generate_dhcpinfo(mac="10:32:54:76:98:ba", ip_address="192.168.122.221"),
    ]
    found = _get_domain_ip_address_leases(macs, leases)
    assert not found


def test_ip_addr_prefer_ipv4():
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
    ip_addr = _get_domain_ip_address_guestinfo(guest_info)
    assert ip_addr == "192.168.122.225"


def test_xml_os_ids_rhel():
    xml = (
        "<domain><metadata>"
        '<libosinfo:libosinfo xmlns:libosinfo="http://libosinfo.org/xmlns/libvirt/domain/1.0">'
        '<libosinfo:os id="http://redhat.com/rhel/10.0"/>'
        "</libosinfo:libosinfo>"
        "</metadata></domain>"
    )
    tree = ET.fromstring(xml)
    versions = _get_domain_xml_os_ids(tree)
    assert versions == ("rhel", "10.0")


def test_xml_os_ids_no_osinfo():
    xml = "<domain><metadata/></domain>"
    tree = ET.fromstring(xml)
    versions = _get_domain_xml_os_ids(tree)
    assert versions == ("", "")


def test_xml_os_ids_no_metadata():
    xml = "<domain><devices/></domain>"
    tree = ET.fromstring(xml)
    versions = _get_domain_xml_os_ids(tree)
    assert versions == ("", "")


def test_xml_mac_one_if():
    xml = (
        "<domain><devices>"
        "<interface type='bridge'>"
        "<mac address='01:23:45:67:89:ab'/>"
        "<source bridge='virbr0'/>"
        "<model type='virtio'/>"
        "<address type='pci' domain='0x0000' bus='0x01' slot='0x00' function='0x0'/>"
        "</interface>"
        "</devices></domain>"
    )
    tree = ET.fromstring(xml)
    macs = _get_domain_mac_addresses(tree)
    assert macs == ["01:23:45:67:89:ab"]


def test_xml_mac_two_if():
    xml = (
        "<domain><devices>"
        "<interface type='bridge'>"
        "<mac address='01:23:45:67:89:ab'/>"
        "<source bridge='virbr0'/>"
        "<model type='virtio'/>"
        "<address type='pci' domain='0x0000' bus='0x01' slot='0x00' function='0x0'/>"
        "</interface>"
        "<interface type='bridge'>"
        "<mac address='ba:98:76:54:32:10'/>"
        "<source bridge='virbr0'/>"
        "<model type='virtio'/>"
        "<address type='pci' domain='0x0000' bus='0x01' slot='0x00' function='0x0'/>"
        "</interface>"
        "</devices></domain>"
    )
    tree = ET.fromstring(xml)
    macs = _get_domain_mac_addresses(tree)
    assert set(macs) == set(["ba:98:76:54:32:10", "01:23:45:67:89:ab"])


def test_xml_mac_no_if():
    xml = (
        "<domain><devices>"
        "<input type='keyboard' bus='ps2'>"
        "<alias name='input2'/>"
        "</input>"
        "</devices></domain>"
    )
    tree = ET.fromstring(xml)
    macs = _get_domain_mac_addresses(tree)
    assert not macs


def test_xml_path_exists():
    xml = """<pool type='dir'><target><path>/tmp/mypath</path></target></pool>"""
    p = _get_pool_path(xml)
    assert p == Path("/tmp/mypath")


def test_xml_path_error():
    xml = """<pool type='dir'><name>mypool</name></pool>"""
    with pytest.raises(VmmgrException):
        _get_pool_path(xml)
