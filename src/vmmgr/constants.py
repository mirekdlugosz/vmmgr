import os

VMMGR_POOL_NAME = os.getenv("VMMGR_POOL", "vmmgr")
VMMGR_TEMPLATE_IMAGES_POOLS = os.getenv("VMMGR_TEMPLATE_IMAGES_POOLS", "default")
XDG_RUNTIME_DIR = os.getenv("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
IMAGE_EXTENSIONS = ("qcow2", "img")
