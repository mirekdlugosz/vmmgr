# vmmgr - Virtual Machine Manager

`vmmgr` is a tool to manage disposable virtual machines. The main goal is to reduce friction - ideally, starting a new virtual machine should require about as much effort as starting a new container. It's a bit like [Vagrant](https://developer.hashicorp.com/vagrant), except it does not need configuration file and does not provide as many features.

`vmmgr` is opinionated. It is a tool created in a specific environment to accommodate specific needs. It is a free software - you can modify it to better fit your use case. If you need more flexibility, you probably should use lower-level tools.

## Dependencies

`vmmgr` manages [libvirt](https://libvirt.org/) virtual machines. libvirt must be installed, configured and running.

`vmmgr` will execute following command-line programs. Most of them are part of libvirt stack, but some might need to be installed separately.

* `qemu-img`
* `virt-install`
* `virsh`
* `osinfo-query`
* `virt-inspector`

`vmmgr` requires [libvirt-python](https://pypi.org/project/libvirt-python/). Unfortunately, `libvirt-python` does not provide binary packages, and `pip install libvirt-python` will fail if you do not have development headers for both libvirt and Python. It is recommended to use `libvirt-python` package provided by your distribution.

[pipx](https://pipx.pypa.io/stable/) is preferred installation method

## Installation

Download copy of this repository and run:

    pipx install --system-site-packages /path/to/vmmgr/source/

`/path/to/vmmgr/source/` is a directory where **this** README file resides.

## Usage

```sh
$ vmmgr create --list
Available VM template images:
 fedora-42-x86_64-kvm.qcow2
 plucky-server-cloudimg-amd64.img
 rhel-10.0-x86_64-kvm.qcow2
$ vmmgr create plucky
  # creates new image on top of template and calls virt-install. commands are printed as they are executed.
  # use vmmgr create --dry-run to only print what would be executed
  # positional argument ("plucky" above) is a template pattern. It is matched against beginning of template image name
  # flags provided after template pattern are passed verbatim to virt-install
  # e.g. start a VM with more memory: vmmgr create fedora --memory 8192
$ vmmgr list
NAME                           STATE           IP ADDRESS                   USER
--------------------------------------------------------------------------------------
plucky-1                       RUNNING         192.168.122.128              ubuntu
  # try also vmmgr list -f shell and vmmgr list -f ansible
$ vmmgr delete --all
```

## Configuration

`vmmgr` creates new image files in a separate libvirt pool. This way it can recognize virtual machines it created, and will not remove machines you started with other tools.

That pool is specified through `VMMGR_POOL` environment variable. By default it is called `vmmgr`.

You can list all libvirt pools with `virsh pool-list --all`. To create a new pool, execute following commands:

```sh
virsh pool-define-as --name vmmgr --type dir --target /path/to/directory/
virsh pool-start vmmgr
virsh pool-autostart vmmgr
```

Template images are read from pools specified by `VMMGR_TEMPLATE_IMAGES_POOLS` environment variable. By default only `default` pool is used. Separate pool names with a comma:

```
export VMMGR_TEMPLATE_IMAGES_POOLS="default,VirtualMachines"
```

`vmmgr create --list` output should be consistent with `virsh vol-list $VMMGR_TEMPLATE_IMAGES_POOLS`. If you can't see image you have put in the pool, run `virsh pool-refresh POOL_NAME`.

## cloud-init

`vmmgr` uses [cloud-init](https://cloudinit.readthedocs.io/) to set new VM hostname and ensure login through SSH is possible.

By default, `vmmgr` will look for `cloud-init/user-data` file relative to source image or inside `vmmgr` libvirt pool.

That is, if source image resolves to `~/.local/share/libvirt/images/fedora-42-x86_64-kvm.qcow2`, `vmmgr` will try to use `~/.local/share/libvirt/images/cloud-init/user-data`. If `vmmgr` **pool** is `~/.local/share/vmmgr/`, then `vmmgr` will try to use `~/.local/share/vmmgr/cloud-init/user-data`.

If neither of these files exist, `vmmgr` will create new `user-data` file with `allow_public_ssh_keys` and `ssh_authorized_keys`, and a list of public keys found in `~/.ssh/`.

If you want to use your own cloud-init file, you can specify it before template pattern:

    vmmgr create --cloud-init /path/to/cloud-init/user-data plucky

## Development

Create new virtual environment and install package with development extras:

```sh
python3 -m venv --system-site-packages ~/.virtualenvs/vmmgr/
. ~/.virtualenvs/vmmgr/bin/activate
pip install -e './[dev]'
```

Run unit tests:

    python -m pytest tests/

Run development version of the tool:

    python -m vmmgr.cli create --list

Linting and formatting, before submitting a patch:

    ruff format
    ruff check
