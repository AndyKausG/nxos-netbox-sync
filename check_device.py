"""
check_device.py — Read-only diff: Netbox intended state vs live switch state.

Default mode (no flags): run checks, print ✅/❌, never write to switch.
--apply: print planned changes, ask for 'yes', then push config via Genie.
--loop: run continuously on --interval seconds (default 300).

Usage:
  python check_device.py --device core-sw
  python check_device.py --device core-sw --apply
  python check_device.py --device core-sw --loop --interval 300
"""
import argparse
import sys
from time import sleep

import utils.get_from_pyats as pyats_utils
import utils.get_from_netbox as nb_utils
import utils.tests as tests
from utils.notifications import notify_team, fail_notification
from utils.logger import log_change
from utils.message_templates import (
    message_vlan_exist_template,
    message_interface_enabled_template,
    message_interface_description_template,
    message_interface_mode_template,
    message_interface_vlan_template,
)


def _collect_planned_changes(vlan_test, enabled_test, desc_test, mode_test, vlan_iface_test):
    """Return a list of human-readable strings describing what --apply would change."""
    changes = []
    for v in vlan_test["FAIL"]:
        changes.append(f"CREATE/UPDATE VLAN {v.vid} ({v.name})")
    for i in enabled_test["FAIL"]:
        changes.append(f"UPDATE Interface {i.name} enabled → {i.enabled}")
    for i in desc_test["FAIL"]:
        changes.append(f"UPDATE Interface {i.name} description → '{i.description}'")
    for i in mode_test["FAIL"]:
        changes.append(f"UPDATE Interface {i.name} switchport mode → {i.mode.label}")
    for i in vlan_iface_test["FAIL"]:
        changes.append(f"UPDATE Interface {i.name} VLAN assignment")
    return changes


def _run_checks(device_name, device, nb, nb_device):
    """Fetch live and intended state, run all tests, print ✅/❌ results."""
    print("\nRetrieving current status from device with pyATS")
    pyats_interfaces = pyats_utils.interfaces_current(device)
    pyats_vlans = pyats_utils.vlans_current(device)

    print("Looking up intended state from Netbox")
    netbox_interfaces = nb_utils.interfaces_sot(nb, nb_device)
    netbox_vlans = nb_utils.vlans_sot(nb, nb_device)

    print("\nVLAN check:")
    vlan_test = tests.verify_vlans_exist(netbox_vlans, pyats_vlans)
    if vlan_test["FAIL"]:
        log_change(device_name, f"VLAN check: {len(vlan_test['FAIL'])} failure(s)")
    fail_notification(vlan_test["FAIL"], message_vlan_exist_template)

    print("\nInterface enabled check:")
    enabled_test = tests.verify_interface_enabled(netbox_interfaces, pyats_interfaces)
    if enabled_test["FAIL"]:
        log_change(device_name, f"Interface enabled check: {len(enabled_test['FAIL'])} failure(s)")
    fail_notification(enabled_test["FAIL"], message_interface_enabled_template)

    print("\nInterface description check:")
    desc_test = tests.verify_interface_descriptions(netbox_interfaces, pyats_interfaces)
    if desc_test["FAIL"]:
        log_change(device_name, f"Interface description check: {len(desc_test['FAIL'])} failure(s)")
    fail_notification(desc_test["FAIL"], message_interface_description_template)

    print("\nInterface mode check:")
    mode_test = tests.verify_interface_mode(netbox_interfaces, pyats_interfaces)
    if mode_test["FAIL"]:
        log_change(device_name, f"Interface mode check: {len(mode_test['FAIL'])} failure(s)")
    fail_notification(mode_test["FAIL"], message_interface_mode_template)

    print("\nInterface VLAN check:")
    vlan_iface_test = tests.verify_interface_vlans(netbox_interfaces, pyats_interfaces, pyats_vlans)
    if vlan_iface_test["FAIL"]:
        log_change(device_name, f"Interface VLAN check: {len(vlan_iface_test['FAIL'])} failure(s)")
    fail_notification(vlan_iface_test["FAIL"], message_interface_vlan_template)

    total_fail = sum(
        len(t["FAIL"])
        for t in (vlan_test, enabled_test, desc_test, mode_test, vlan_iface_test)
    )
    if total_fail == 0:
        print(f"\n✅ All checks passed for {device_name}")
    else:
        print(f"\n❌ {total_fail} check(s) failed for {device_name}")

    return vlan_test, enabled_test, desc_test, mode_test, vlan_iface_test


def _apply_changes(device_name, device, vlan_test, enabled_test, desc_test, mode_test, vlan_iface_test):
    """Push all planned changes to the switch. Called only after user confirmation."""
    if vlan_test["FAIL"]:
        print("\nApplying VLAN changes...")
        pyats_utils.vlans_configure(device, vlan_test["FAIL"])
        log_change(device_name, f"VLAN configuration updated ({len(vlan_test['FAIL'])} VLAN(s))")
        notify_team(f"[{device_name}] VLAN configuration updated")

    if enabled_test["FAIL"]:
        print("\nApplying interface enabled state changes...")
        pyats_utils.interface_enable_state_configure(device, enabled_test["FAIL"])
        log_change(device_name, f"Interface enabled states updated ({len(enabled_test['FAIL'])} interface(s))")
        notify_team(f"[{device_name}] Interface enabled states updated")

    if desc_test["FAIL"]:
        print("\nApplying interface description changes...")
        pyats_utils.interface_description_configure(device, desc_test["FAIL"])
        log_change(device_name, f"Interface descriptions updated ({len(desc_test['FAIL'])} interface(s))")
        notify_team(f"[{device_name}] Interface descriptions updated")

    if mode_test["FAIL"] or vlan_iface_test["FAIL"]:
        print("\nApplying switchport changes...")
        pyats_utils.interface_switchport_configure(device, mode_test["FAIL"])
        pyats_utils.interface_switchport_configure(device, vlan_iface_test["FAIL"])
        log_change(device_name, "Interface switchport configurations updated")
        notify_team(f"[{device_name}] Interface switchport configurations updated")


def main():
    parser = argparse.ArgumentParser(
        description="Check Netbox intended state vs live IOS/IOS-XE switch state."
    )
    parser.add_argument("--device", required=True, help="Device name from testbed.yaml")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Push diff to switch (requires explicit 'yes' confirmation)",
    )
    parser.add_argument(
        "--loop",
        action="store_true",
        help="Run continuously at --interval seconds",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=300,
        metavar="SECONDS",
        help="Loop interval in seconds (default: 300, requires --loop)",
    )
    args = parser.parse_args()

    # Connect to device via testbed.yaml
    print(f"Connecting to {args.device}...")
    try:
        device = pyats_utils.connect(args.device)
    except KeyError as exc:
        print(f"ERROR: {exc}")
        sys.exit(1)

    # Connect to Netbox
    nb = nb_utils.connect()
    nb_device = nb_utils.get_device(nb, args.device)
    if not nb_device:
        print(
            f"ERROR: Device '{args.device}' not found in Netbox. "
            "Run import_device.py first."
        )
        sys.exit(1)

    notify_team(f"[{args.device}] Starting check run.")

    while True:
        print(f"\n{'=' * 60}")
        print(f"Device: {args.device}  |  Mode: {'apply' if args.apply else 'check-only'}")
        print("=" * 60)

        results = _run_checks(args.device, device, nb, nb_device)
        vlan_test, enabled_test, desc_test, mode_test, vlan_iface_test = results

        if args.apply:
            planned = _collect_planned_changes(*results)
            if not planned:
                print("\nNo changes needed.")
            else:
                print(f"\nPlanned changes for {args.device}:")
                for change in planned:
                    print(f"  {change}")
                try:
                    confirm = input("\nType 'yes' to apply: ").strip().lower()
                except (EOFError, KeyboardInterrupt):
                    print("\nApply cancelled.")
                    confirm = ""
                if confirm == "yes":
                    _apply_changes(
                        args.device, device,
                        vlan_test, enabled_test, desc_test, mode_test, vlan_iface_test,
                    )
                    print(f"\n✅ {len(planned)} change(s) applied to {args.device}")
                else:
                    print("Apply cancelled.")

        if not args.loop:
            break

        print(f"\nNext check in {args.interval}s. Press Ctrl+C to stop.")
        sleep(args.interval)


if __name__ == "__main__":
    main()
