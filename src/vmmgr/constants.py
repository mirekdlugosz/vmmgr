import os

VMMGR_POOL_NAME = os.getenv("VMMGR_POOL", "vmmgr")
VMMGR_TEMPLATE_IMAGES_POOLS = os.getenv("VMMGR_TEMPLATE_IMAGES_POOLS", "default")
XDG_RUNTIME_DIR = os.getenv("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
IMAGE_EXTENSIONS = ("qcow2", "img")
LIBVIRT_CONNECTION_URIS = ("qemu:///session", "qemu:///system")
LIBVIRT_XML_NAMESPACES = {
    "libosinfo": "http://libosinfo.org/xmlns/libvirt/domain/1.0",
}

USER_TEMPLATE_MAP = {
    "dsc": "dscci",
}

USER_OS_MAP = {
    "fedora": "fedora",
    "ubuntu": "ubuntu",
    "rhel": "cloud-user",
}
