# netbox-sync

[![published](https://static.production.devnetcloud.com/codeexchange/assets/images/devnet-published.svg)](https://developer.cisco.com/codeexchange/github/repo/hpreston/nxos-netbox-sync)

Keep Cisco switch configurations aligned with [Netbox](https://netbox.dev) as Source of Truth,
using [pyATS/Genie](https://developer.cisco.com/pyats/) for live device state and
[pynetbox](https://github.com/netbox-community/pynetbox) for Netbox API access.

**Fork of [hpreston/nxos-netbox-sync](https://github.com/hpreston/nxos-netbox-sync)** —
extended to support IOS/IOS-XE (Cisco C1000 series) and a safe, read-only-by-default
execution model. Many thanks to Hank Preston for the original concept and implementation.

> **USE AT YOUR OWN RISK.**
> This tool can push configuration changes to live network switches.
> The author assumes no responsibility for outages, data loss, or any other damage
> caused by running this code in your environment.
> Always test in a lab before touching production. **You have been warned.**

---

## What it does

```
============================================================
Device: core-sw  |  Mode: check-only
============================================================

VLAN check:
✅ VLAN 99 (Management) exists with correct name on switch
✅ VLAN 100 (Home) exists with correct name on switch
❌ VLAN 130 (IoT) MISSING from switch

Interface enabled check:
✅ GigabitEthernet1/0/1 was correctly found to be UP/UP on switch
✅ GigabitEthernet1/0/2 was correctly found to be UP/UP on switch

Interface description check:
✅ GigabitEthernet1/0/1 has the correct description configured on switch
❌ GigabitEthernet1/0/5 incorrectly has NO description on switch. It should be 'AP Floor 2'

❌ 2 check(s) failed for core-sw
```

---

## Supported platforms

| Platform | Status |
|---|---|
| Cisco IOS / IOS-XE (C1000 series) | ✅ primary target |
| Cisco NX-OS | ✅ supported (original hpreston implementation) |

Verified Genie parsers (IOS-XE, `os: iosxe`): `show version`, `show vlan brief`,
`show interfaces`, `show interfaces switchport`.

---

## Safety model

| Mode | What it does | How to invoke |
|---|---|---|
| **check** (default) | Reads device state, diffs against Netbox, prints ✅/❌. Never writes. | `python check_device.py --device core-sw` |
| **apply** | Prints planned changes, asks for `yes`, then pushes config. | `python check_device.py --device core-sw --apply` |
| **loop** | Runs check continuously at a configurable interval. | `python check_device.py --device core-sw --loop --interval 300` |
| **import** | One-time initial import of switch state into Netbox. | `python import_device.py --device core-sw` |

**Non-negotiable rules:**
- Read-only by default — no writes without `--apply`
- Every apply run prints a full diff and asks for explicit `yes` before executing
- Import is always manual — no scheduler, no webhook, no automation trigger
- No auto-apply loops — the original `while True: sleep(10)` pattern is removed

---

## Prerequisites

- Python 3.10+
- pyATS / Genie (see `requirements.txt`)
- A running [Netbox](https://github.com/netbox-community/netbox-docker) instance
- Device and Device Type must already exist in Netbox before running `import_device.py`

For IOS/C1000 with older SSH algorithms, configure legacy crypto on your Linux host:

```bash
sudo update-crypto-policies --set LEGACY   # AlmaLinux / RHEL 9
```

And add to `~/.ssh/config`:

```
Host <your-switch>
    KexAlgorithms +diffie-hellman-group14-sha1
    HostKeyAlgorithms +ssh-rsa
```

---

## Setup

### 1. Clone and install

```bash
git clone https://github.com/AndyKausG/nxos-netbox-sync.git
cd nxos-netbox-sync
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure testbed.yaml

Copy the example and fill in your device details:

```bash
cp testbed.yaml.example testbed.yaml   # then edit testbed.yaml
```

```yaml
# testbed.yaml — not committed, see testbed.yaml.example
testbed:
  name: testbed
  credentials:
    default:
      username: "%ENV{SWITCH_USERNAME}"
      password: "%ENV{SWITCH_PASSWORD}"

devices:
  core-sw:                      # must match --device argument
    os: iosxe                   # use iosxe for C1000 IOS 15.2 — parser coverage is better
    platform: iosxe
    type: switch
    connections:
      default:
        protocol: ssh
        ip: "%ENV{SWITCH_MGMT_IP}"   # or hardcode the management IP
```

**Alternative — generate from Netbox automatically:**

```bash
python generate_testbed.py     # reads NETBOX_URL, NETBOX_TOKEN, SWITCH_HOSTNAME from src_env
```

### 3. Set environment variables

```bash
cp src_env.template src_env   # then edit src_env
source src_env
```

Minimum required:

```bash
export NETBOX_URL="https://<your-netbox>"
export NETBOX_TOKEN="<your-token>"
export SWITCH_USERNAME="<username>"
export SWITCH_PASSWORD="<password>"
export SWITCH_MGMT_IP="<management-ip>"   # used by testbed.yaml or generate_testbed.py
export SWITCH_HOSTNAME="<device-name>"    # used by generate_testbed.py to filter Netbox devices
```

Optional — notifications via [ntfy](https://ntfy.sh):

```bash
export NOTIFY_BACKEND=ntfy
export NTFY_URL=https://ntfy.sh        # or self-hosted
export NTFY_TOPIC=netbox-sync-alerts
```

Optional — log applied changes to a file:

```bash
export LOG_FILE=/var/log/netbox-sync/changes.log
```

---

## Generate testbed from Netbox

Instead of writing `testbed.yaml` by hand, you can generate it automatically from your
Netbox inventory using `generate_testbed.py`:

```bash
# With src_env already sourced:
python generate_testbed.py

# Writes testbed.yaml in the current directory.
# SWITCH_HOSTNAME filters to a single device; omit it to pull all devices.
```

The script uses `pyats.contrib.creators.netbox` (included in `pyats[full]`) to query
Netbox and produce a testbed with `%ENV{SWITCH_USERNAME}` / `%ENV{SWITCH_PASSWORD}`
credential placeholders — no credentials are embedded in the file.

---

## Usage

### Initial import (run once)

Reads live state from the switch and populates Netbox.
**Device and Device Type must already exist in Netbox before running.**
Skips objects that already exist — safe to re-run.

```bash
# Preview what will be written (no changes)
python import_device.py --device core-sw --dry-run

# Run import (prints plan, asks for 'yes')
python import_device.py --device core-sw
```

What it imports: chassis serial number, all interfaces, all VLANs (legacy VLANs ≥ 1002 skipped).

### Check (read-only)

```bash
python check_device.py --device core-sw
```

Checks: VLAN existence and name, interface enabled state, interface descriptions,
switchport mode (access/trunk), access VLAN and trunk VLANs.

### Apply changes

```bash
python check_device.py --device core-sw --apply
```

Prints all planned changes first. Requires typing `yes` to proceed.

```
Planned changes for core-sw:
  CREATE/UPDATE VLAN 130 (IoT)
  UPDATE Interface GigabitEthernet1/0/5 description → 'AP Floor 2'

Type 'yes' to apply:
```

### Continuous monitoring

```bash
python check_device.py --device core-sw --loop --interval 300
```

Runs checks every 300 seconds. Stop with `Ctrl-C`.
Does NOT apply changes automatically — add `--apply` only if you want interactive
confirmation on each cycle (useful for a supervised maintenance window).

---

## Repository structure

```
netbox-sync/
├── import_device.py        # One-time Switch → Netbox import
├── check_device.py         # Main check / apply / loop entrypoint
├── generate_testbed.py     # Generate testbed.yaml from Netbox (uses pyats.contrib)
├── requirements.txt
├── testbed.yaml            # NOT committed — generate via generate_testbed.py or copy from testbed.yaml.example
├── testbed.yaml.example    # Manual template (IOS-XE, env-var placeholders)
├── src_env.template        # Environment variable template
├── templates/              # Jinja2 notification message templates
└── utils/
    ├── get_from_pyats.py   # Device state via pyATS/Genie (platform-aware)
    ├── get_from_netbox.py  # Intended state from Netbox API
    ├── tests.py            # Diff / verification logic
    ├── notifications.py    # ntfy | none backends (NOTIFY_BACKEND)
    ├── logger.py           # Rotating file logger for applied changes
    └── message_templates.py
```

---

## Caveats

- VLAN-to-device mapping uses the **Site** as the link: every VLAN configured for the
  device's site in Netbox is checked against the switch. Devices sharing a site but
  requiring different VLAN sets need a code change.
- Only checks that Netbox VLANs are present on the switch. Extra VLANs on the switch
  that are absent from Netbox are ignored (not removed).
- IOS C1000 native VLAN verification on trunks is currently skipped due to a known
  Genie ops model limitation — marked with a comment in `utils/tests.py`.

---

## License

MIT — see `LICENSE`.

Original implementation by [Hank Preston, Cisco DevNet](https://github.com/hpreston/nxos-netbox-sync).
