#!/usr/bin/env python3
"""
generate_testbed.py — Generate testbed.yaml from Netbox inventory.

Uses pyats.contrib.creators.netbox (included in pyats[full]) to pull device
data from Netbox and write a testbed.yaml with %ENV{...} credential placeholders.

Environment variables (set via src_env or export):
  NETBOX_URL      — Netbox base URL, e.g. https://netbox.example.com
  NETBOX_TOKEN    — Netbox API token
  SWITCH_HOSTNAME — (optional) filter to a single device by name;
                    omit to pull all devices accessible with the token
  SWITCH_USERNAME / SWITCH_PASSWORD — referenced as %ENV{...} in the output,
                    not embedded in the file

Usage:
  python generate_testbed.py
  python generate_testbed.py --output custom_testbed.yaml
"""
import argparse
import os
import sys

from pyats.contrib.creators.netbox import Netbox


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate testbed.yaml from Netbox inventory"
    )
    parser.add_argument(
        "--output",
        default="testbed.yaml",
        help="Output file path (default: testbed.yaml)",
    )
    args = parser.parse_args()

    netbox_url = os.environ.get("NETBOX_URL")
    netbox_token = os.environ.get("NETBOX_TOKEN")
    if not netbox_url or not netbox_token:
        print(
            "ERROR: NETBOX_URL and NETBOX_TOKEN must be set in the environment.\n"
            "       Run: source src_env",
            file=sys.stderr,
        )
        sys.exit(1)

    hostname = os.environ.get("SWITCH_HOSTNAME", "").strip()
    url_filter = f"name={hostname}" if hostname else None

    print(f"Connecting to Netbox at {netbox_url} ...")
    if hostname:
        print(f"Filtering devices by name: {hostname}")
    else:
        print("No SWITCH_HOSTNAME set — pulling all devices.")

    nb = Netbox(
        netbox_url=netbox_url,
        user_token=netbox_token,
        def_user="%ENV{SWITCH_USERNAME}",
        def_pass="%ENV{SWITCH_PASSWORD}",
        ssl_verify=False,
        url_filter=url_filter,
        topology=True,
    )
    try:
        nb._generate()
    except TypeError:
        device_hint = f" matching '{hostname}'" if hostname else ""
        print(
            f"ERROR: No devices found in Netbox{device_hint}.\n"
            "       Add devices in Netbox first, then re-run.",
            file=sys.stderr,
        )
        sys.exit(1)

    nb.to_testbed_file(args.output)
    print(f"Done — written to: {args.output}")


if __name__ == "__main__":
    main()
