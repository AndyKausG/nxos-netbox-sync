"""
utils/get_from_netbox.py — pynetbox helpers.

Use connect() to get an api object, get_device(nb, name) to look up the device.
All query functions take explicit nb and nb_device parameters.
"""
import os
import sys
import pynetbox


def connect():
    """Connect to Netbox and return a pynetbox.api object."""
    url = os.environ.get("NETBOX_URL")
    token = os.environ.get("NETBOX_TOKEN")
    if not url or not token:
        print("ERROR: NETBOX_URL and NETBOX_TOKEN environment variables must be set.")
        sys.exit(1)
    return pynetbox.api(url, token=token)


def get_device(nb, device_name):
    """Return the Netbox device record for device_name, or None."""
    return nb.dcim.devices.get(name=device_name)


def interfaces_sot(nb, nb_device):
    """Return Netbox interfaces for the given device."""
    return nb.dcim.interfaces.filter(device_id=nb_device.id)


def vlans_sot(nb, nb_device):
    """Return Netbox VLANs for the site the device belongs to."""
    return nb.ipam.vlans.filter(site_id=nb_device.site.id)
