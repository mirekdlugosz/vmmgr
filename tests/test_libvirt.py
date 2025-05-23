from pathlib import Path

import pytest

from vmmgr.libvirt import _get_domain_disks
from vmmgr.libvirt import _get_domain_ip_address
from vmmgr.libvirt import _get_pool_path
from vmmgr.types import VmmgrException


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


def test_ip_addr_no_if():
    guest_info = {"noif": "key"}
    ip_addr = _get_domain_ip_address(guest_info)
    assert ip_addr is None


def test_ip_addr_only_lo():
    guest_info = {"if.0.addr.0.addr": "127.0.0.1", "if.0.addr.0.type": "ipv4", "if.0.name": "lo"}
    ip_addr = _get_domain_ip_address(guest_info)
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
    ip_addr = _get_domain_ip_address(guest_info)
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
    ip_addr = _get_domain_ip_address(guest_info)
    assert ip_addr == "192.168.122.225"


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
    ip_addr = _get_domain_ip_address(guest_info)
    assert ip_addr == "192.168.122.225"


def test_xml_path_exists():
    xml = """<pool type='dir'><target><path>/tmp/mypath</path></target></pool>"""
    p = _get_pool_path(xml)
    assert p == Path("/tmp/mypath")


def test_xml_path_error():
    xml = """<pool type='dir'><name>mypool</name></pool>"""
    with pytest.raises(VmmgrException):
        _get_pool_path(xml)
