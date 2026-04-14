"""
import_device.py — One-time initial import: Switch → Netbox.

Reads live state from the switch via pyATS/Genie and populates Netbox.
NEVER overwrites existing Netbox data — skips objects that already exist.
Always manual, never automated.

Prerequisites:
  - Device and Device Type must already exist in Netbox
  - testbed.yaml must have the device with os: iosxe
  - NETBOX_URL and NETBOX_TOKEN must be set in the environment

Usage:
  python import_device.py --device core-sw
  python import_device.py --device core-sw --dry-run
"""
import argparse
import sys
import os

import pynetbox
from genie.testbed import load as load_testbed

# VLANs with vid >= 1002 are internal/legacy IOS VLANs (1002-1005: fddi/token-ring).
LEGACY_VLAN_MIN = 1002

# Interface name prefix → Netbox interface type slug.
_IFACE_TYPE_MAP = [
    ("GigabitEthernet", "1000base-t"),
    ("TenGigabitEthernet", "10gbase-x-sfpp"),
    ("HundredGigE", "100gbase-x-cfp"),
    ("FortyGigabitEthernet", "40gbase-x-qsfpp"),
    ("FastEthernet", "100base-tx"),
    ("Port-channel", "lag"),
    ("Vlan", "virtual"),
    ("Loopback", "virtual"),
    ("Tunnel", "virtual"),
    ("Null", "virtual"),
    ("Management", "1000base-t"),
]


def _iface_type(name):
    for prefix, slug in _IFACE_TYPE_MAP:
        if name.startswith(prefix):
            return slug
    return "other"


def _get_serial(device):
    """Parse 'show version' and return the chassis serial number."""
    version = device.parse("show version")
    v = version.get("version", {})
    # Key name varies slightly across IOS/IOS-XE variants.
    for key in ("chassis_sn", "processor_board_id", "chassis_serial", "system_sn"):
        if v.get(key):
            return v[key]
    return ""


def _get_vlans(device):
    """Return sorted list of (vid, name) from switch, skipping legacy VLANs."""
    vlans_ops = device.learn("vlan")
    result = []
    for vid_str, details in vlans_ops.info.get("vlans", {}).items():
        vid = int(vid_str)
        if vid >= LEGACY_VLAN_MIN:
            continue
        name = details.get("name", f"VLAN{vid:04d}")
        result.append((vid, name))
    return sorted(result)


def _get_interfaces(device):
    """Return sorted list of interface names from 'show interfaces'."""
    iface_ops = device.learn("interface")
    return sorted(iface_ops.info.keys())


def main():
    parser = argparse.ArgumentParser(
        description=(
            "One-time import of switch state into Netbox. "
            "Skips objects that already exist (idempotent). "
            "Device must already exist in Netbox before running."
        )
    )
    parser.add_argument("--device", required=True, help="Device name from testbed.yaml")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned writes without making any changes",
    )
    args = parser.parse_args()

    # --- Connect to device ---
    testbed = load_testbed("testbed.yaml")
    if args.device not in testbed.devices:
        print(f"ERROR: Device '{args.device}' not found in testbed.yaml")
        sys.exit(1)

    print(f"Connecting to {args.device}...")
    device = testbed.devices[args.device]
    device.connect(learn_hostname=True, log_stdout=False)

    # --- Connect to Netbox ---
    netbox_url = os.environ.get("NETBOX_URL")
    netbox_token = os.environ.get("NETBOX_TOKEN")
    if not netbox_url or not netbox_token:
        print("ERROR: NETBOX_URL and NETBOX_TOKEN environment variables must be set.")
        sys.exit(1)

    nb = pynetbox.api(netbox_url, token=netbox_token)

    # --- Device must already exist in Netbox ---
    nb_device = nb.dcim.devices.get(name=args.device)
    if not nb_device:
        print(f"ERROR: Device '{args.device}' not found in Netbox.")
        print("       Create the Device (and its Device Type) in Netbox first, then re-run.")
        sys.exit(1)

    print(f"Found '{args.device}' in Netbox  (id={nb_device.id}, site={nb_device.site})")

    # --- Parse live switch state ---
    print("Parsing switch state (show version, show vlan, show interfaces)...")
    serial = _get_serial(device)
    switch_vlans = _get_vlans(device)
    switch_interfaces = _get_interfaces(device)

    print(f"  Serial:     {serial or '(not found)'}")
    print(f"  VLANs:      {len(switch_vlans)}")
    print(f"  Interfaces: {len(switch_interfaces)}")

    # --- Plan writes ---
    planned = []  # list of (label, callable)

    # Serial number — update only if switch has one and Netbox doesn't match
    if serial and nb_device.serial != serial:
        label = f"UPDATE Device {args.device}: serial → {serial}"
        planned.append((label, lambda s=serial: _write_serial(nb_device, s)))

    # VLANs — create only if not already in Netbox for this site
    existing_vids = {
        v.vid for v in nb.ipam.vlans.filter(site_id=nb_device.site.id)
    }
    for vid, name in switch_vlans:
        if vid not in existing_vids:
            label = f"CREATE VLAN {vid} ({name})"
            planned.append((label, lambda v=vid, n=name: _write_vlan(nb, nb_device, v, n)))

    # Interfaces — create only if not already on this device in Netbox
    existing_iface_names = {
        i.name for i in nb.dcim.interfaces.filter(device_id=nb_device.id)
    }
    for iface_name in switch_interfaces:
        if iface_name not in existing_iface_names:
            itype = _iface_type(iface_name)
            label = f"CREATE Interface {iface_name} (type={itype})"
            planned.append((label, lambda n=iface_name, t=itype: _write_interface(nb, nb_device, n, t)))

    # --- Print plan ---
    if not planned:
        print("\nNetbox is already up to date — nothing to write.")
        return

    print(f"\nPlanned writes to Netbox ({len(planned)} object(s)):")
    for label, _ in planned:
        print(f"  {label}")

    if args.dry_run:
        print("\n[dry-run] No changes made.")
        return

    # --- Confirmation ---
    try:
        confirm = input("\nType 'yes' to write to Netbox: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("\nImport cancelled.")
        return

    if confirm != "yes":
        print("Import cancelled.")
        return

    # --- Execute ---
    print("\nWriting to Netbox...")
    errors = 0
    for label, fn in planned:
        try:
            fn()
            print(f"  ✅ {label}")
        except Exception as exc:
            print(f"  ❌ {label}  →  {exc}")
            errors += 1

    if errors:
        print(f"\nCompleted with {errors} error(s). Re-run to retry failed objects.")
        sys.exit(1)
    else:
        print(f"\nDone. {len(planned)} object(s) written to Netbox.")


def _write_serial(nb_device, serial):
    nb_device.serial = serial
    nb_device.save()


def _write_vlan(nb, nb_device, vid, name):
    nb.ipam.vlans.create(
        vid=vid,
        name=name,
        site=nb_device.site.id,
        status="active",
    )


def _write_interface(nb, nb_device, name, iface_type_slug):
    nb.dcim.interfaces.create(
        device=nb_device.id,
        name=name,
        type=iface_type_slug,
    )


if __name__ == "__main__":
    main()
