# AGENTS.md – netbox-sync

## Attribution & License

This project is a fork of [hpreston/nxos-netbox-sync](https://github.com/hpreston/nxos-netbox-sync)
by Hank Preston (Cisco DevNet). Many thanks to Hank for the original concept and implementation.

The original code demonstrated how to keep NX-OS switch configuration aligned with a Netbox
Source of Truth using pyATS/Genie. This fork extends the project to support multiple platforms
(NX-OS and IOS/IOS-XE) and adds a safe, read-only-by-default execution model.

Licensed under the MIT License — see `LICENSE`.

---

## Project Goal

Keep Cisco switch configurations aligned with Netbox as Source of Truth, using pyATS/Genie
for live device state and pynetbox for Netbox API access.

**Supported platforms:**
- Cisco NX-OS (original, hpreston)
- Cisco IOS / IOS-XE (extended, this fork) — primary target: C1000 switches

**Two use cases:**
- **Kucher-Haus** (homelab/residential): C1000-48P-4G-L (core-sw), C1000-8P-E-2G-L (access-sw)
- **DLA Marbach** (enterprise): NX-OS + IOS production environment

---

## Security — No Private Data in Repository

The following MUST NEVER appear in any committed file:

- IP addresses of production devices (use env vars or config files listed in `.gitignore`)
- Hostnames that reveal internal infrastructure
- Usernames, passwords, API tokens, SSH keys
- Internal domain names (e.g. `<INTERNAL_DOMAIN>`, `<SITE2_INTERNAL_DOMAIN>`)
- Site-specific VLAN IDs or network ranges

**Pattern:** All site-specific data goes into `src_env` (gitignored) or `testbed.yaml` (gitignored).
Only `*.example` and `*.template` files are committed.

**`.gitignore` must cover (do not modify these entries):**
```gitignore
# Credentials & secrets
src_env
.env
*.token
*.key

# Site-specific config (never commit real values)
testbed.yaml
config.yml

# Python
__pycache__/
*.pyc
.venv/
venv/

# pyATS artifacts
*.txt.lock
/logs/
/archive/
```

**Template files (always commit these):**

Every gitignored config file MUST have a committed `*.template` counterpart with:
- All keys present, values replaced with `<PLACEHOLDER>` or `%ENV{VAR_NAME}`
- A comment block at the top explaining each variable
- No real IPs, hostnames, usernames, domains, or tokens

```
src_env.template      → copy to src_env, fill in values
testbed.yaml.template → copy to testbed.yaml, fill in values  
config.yml.template   → copy to config.yml, fill in values
```

**Pre-commit check (Claude Code must run before every commit):**
```bash
grep -rE '(172\.|10\.|192\.168\.|\.internal|\.local)' --include="*.py" --include="*.yml" --include="*.yaml" --include="*.json" . \
  | grep -v ".template" | grep -v ".example" | grep -v "CLAUDE.md" | grep -v "AGENTS.md"
```
If this returns any results → STOP, do not commit.

---

## Execution Model

### Import (initial, one-time only)
Reads live state from switches and populates Netbox. **Always manual, never automated.**

```bash
python import_device.py --device core-sw
```

- Requires Netbox to have Device + Device Type already configured
- Skips if object already exists in Netbox (idempotent, no overwrites)
- Prints what it would create, asks for confirmation before writing

### Check (read-only, default mode)
Compares Netbox intended state vs live switch state. **Never writes to switch.**

```bash
python check_device.py --device core-sw
```

### Apply (optional, explicit only)
Pushes diff to switch. **Requires `--apply` flag + interactive confirmation.**

```bash
python check_device.py --device core-sw --apply
```

Prints planned changes, waits for `yes` before executing.

### Loop (triggered, not automatic)
Continuous check mode for monitoring — **must be explicitly triggered**, never started automatically.

```bash
python check_device.py --device core-sw --loop --interval 300
```

---

## Demo vs Production Mode

The tool detects its execution context via the `NETBOX_SYNC_MODE` environment variable:

- `NETBOX_SYNC_MODE=demo` — uses sandbox/demo Netbox, safe to experiment, no confirmation prompts
- `NETBOX_SYNC_MODE=production` — requires explicit `--apply`, confirmation prompts, verbose logging

If `NETBOX_SYNC_MODE` is not set, the tool defaults to **read-only** and prints a warning.

---

## Safety Rules — Non-Negotiable

1. **Read-only by default.** The tool NEVER writes to a switch unless `--apply` is explicitly passed.
2. **Dry-run first.** Every run prints a full diff (✅/❌) before any changes.
3. **No auto-apply loops.** The original `while True: sleep(10)` pattern is removed. Runs are
   triggered manually or via scheduled job with explicit intent.
4. **Production switches are live.** core-sw and access-sw carry production traffic.
   Any write operation must be reviewed by the operator first.
5. **Confirmation prompt before apply.** When `--apply` is passed, the tool prints the planned
   changes and asks for explicit `yes` confirmation before executing.
6. **Import is always manual.** No scheduler, no webhook, no automation triggers import.
7. **No private data in code.** All credentials, IPs, hostnames via env vars only.

---

## Repository Structure

```
netbox-sync/
├── AGENTS.md                  # This file
├── LICENSE                    # MIT
├── README.md
├── requirements.txt
├── check_device.py            # Main entrypoint
├── testbed.yaml               # pyATS testbed (not committed, see testbed.yaml.example)
├── testbed.yaml.example       # Template
├── src_env.template           # Environment variable template
├── platforms/
│   ├── nxos/                  # NX-OS specific parsers/config builders (original)
│   └── ios/                   # IOS/IOS-XE specific parsers/config builders (new)
└── utils/
    ├── get_from_pyats.py      # Device state via pyATS (platform-aware)
    ├── get_from_netbox.py     # Intended state from Netbox API
    └── tests.py               # Diff/verification logic
```

---

## Platform Detection

Platform is determined from the testbed.yaml `os` field:
- `nxos` → use `platforms/nxos/`
- `iosxe` or `ios` → use `platforms/ios/`

**Important for IOS (C1000):**
- Use `os: iosxe` in testbed.yaml — Genie parser coverage is better than `os: ios`
- C1000 IOS 15.2(7) output is compatible with iosxe parsers
- SSH requires legacy algorithms — see SSH Config below

---

## Environment Variables

```bash
# Netbox
NETBOX_URL="https://<NETBOX_INTERNAL_URL>"
NETBOX_TOKEN="..."

# Switch credentials (used via testbed.yaml %ENV{} references)
CISCO_USER="<SWITCH_USER>"
CISCO_PASS="..."

# Optional: Netbox site filter
NETBOX_SITE="<NETBOX_SITE>"

# Notifications
NOTIFY_BACKEND=none           # none | ntfy
NTFY_URL="https://<NTFY_URL>" # ntfy server (self-hosted or ntfy.sh)
NTFY_TOPIC="<NTFY_TOPIC>"     # ntfy topic name

# Logging (applied changes only)
LOG_FILE="<LOG_FILE_PATH>"    # e.g. /var/log/netbox-sync/changes.log
                               # Omit to write to stdout only
```

---

## Testbed (IOS/C1000)

```yaml
devices:
  core-sw:
    alias: core-sw
    connections:
      cli:
        ip: <SWITCH_MGMT_IP_1>
        protocol: ssh
    credentials:
      default:
        username: "%ENV{CISCO_USER}"
        password: "%ENV{CISCO_PASS}"
    os: iosxe
    platform: iosxe
    type: switch
  access-sw:
    alias: access-sw
    connections:
      cli:
        ip: <SWITCH_MGMT_IP_2>
        protocol: ssh
    credentials:
      default:
        username: "%ENV{CISCO_USER}"
        password: "%ENV{CISCO_PASS}"
    os: iosxe
    platform: iosxe
    type: switch
```

---

## SSH Config (netbox01 / AlmaLinux 9)

AlmaLinux 9 requires LEGACY crypto policy for old Cisco IOS SSH algorithms:

```bash
sudo update-crypto-policies --set LEGACY
```

`~/.ssh/config`:

```
Host core-sw
    HostName <SWITCH_MGMT_IP_1>
    User <SWITCH_USER>
    KexAlgorithms +diffie-hellman-group14-sha1
    HostKeyAlgorithms +ssh-rsa

Host access-sw
    HostName <SWITCH_MGMT_IP_2>
    User <SWITCH_USER>
    KexAlgorithms +diffie-hellman-group14-sha1
    HostKeyAlgorithms +ssh-rsa
```

---

## Verified Genie Parsers (IOS/C1000, pyATS 25.9)

| Command | Parser | Status |
|---|---|---|
| `show version` | iosxe | ✅ verified |
| `show vlan brief` | iosxe | ✅ verified |
| `show interfaces` | iosxe | ✅ verified |
| `show ip interface brief` | iosxe | to be verified |
| `show interfaces switchport` | iosxe | to be verified |

---

## Netbox Data Model (Kucher-Haus)

**Devices:**
- `core-sw` — C1000-48P-4G-L, <SWITCH_MGMT_IP_1>, Serial: <SERIAL_NUMBER_CORE_SW>
- `access-sw` — C1000-8P-E-2G-L, <SWITCH_MGMT_IP_2>, Serial: <SERIAL_NUMBER_ACCESS_SW>

**VLANs:** 99 (Management), 100 (Home), 101–104 (Tenant), 110 (SharedSvcs),
120 (Guest), 130 (IoT), 140 (HomeLab), 150 (DMZ), 160 (Quarantäne), 200 (Voice)

**Netbox URL:** `https://<NETBOX_INTERNAL_URL>`

---

## Roadmap / Planned Features

### Phase 1 — Core (current)
- [x] PyATS/Genie parser setup (IOS/IOS-XE, C1000)
- [x] Read-only check mode
- [ ] Initial import script (Netbox → populate from switch)
- [ ] `--apply` mode mit Confirmation Prompt
- [ ] `--loop` mode mit `--interval`
- [ ] Demo vs Production mode (`NETBOX_SYNC_MODE`)
- [ ] NX-OS platform support (from original hpreston code)

### Phase 2 — Webhook Integration
Netbox Event Rules triggern das Tool automatisch bei Änderungen:

```
Netbox: Objekt geändert (VLAN, Interface, Device)
  → Event Rule → Webhook POST → netbox01:8000/trigger
  → FastAPI Listener empfängt Request
  → Startet check_device.py --device <device>
  → Ergebnis als Netbox Journal Entry oder Notification
```

- [ ] FastAPI Webhook Listener (`webhook_listener.py`)
- [ ] Netbox Event Rule Dokumentation
- [ ] ntfy alert on detected drift (NOTIFY_BACKEND=ntfy)
- [ ] Optional: Bestätigung via ntfy/webhook vor --apply

### Phase 3 — Git-basierter Rollback
Oxidized läuft bereits und committed Switch-Configs in `switches.git`.
Nach jedem `--apply` wird der neue Ist-Zustand von Oxidized automatisch erfasst.

```
--apply schreibt Config auf Switch
  → Oxidized polling erkennt Änderung
  → Commit in switches.git (automatisch)
  → Rollback: git show / git diff → Config manuell zurückspielen
```

Geplant: Rollback-Helper Script

```bash
# Letzten Zustand anzeigen
python rollback.py --device core-sw --show

# Auf letzten Git-Commit zurücksetzen
python rollback.py --device core-sw --apply
```

- [ ] `rollback.py` — liest Config aus Oxidized Git, spielt zurück via PyATS
- [ ] Oxidized Git-Integration dokumentieren
- [ ] Pre/Post-Change Snapshots (`genie learn` vor und nach --apply)

### Phase 4 — Netbox Config Rendering (optional)
Netbox kann Jinja2-Templates rendern und Config direkt als Source of Truth nutzen:

```
Netbox Jinja2 Template
  → Rendered Config (per API abrufbar)
  → netbox-sync vergleicht mit Ist-Zustand
  → Bei Abweichung: --apply oder Notification
```

- [ ] Config Templates in Netbox anlegen
- [ ] Rendered Config via API abrufen und als Soll-Zustand nutzen

---

## What Agents Must NOT Do

- Never write to a switch without `--apply` flag
- Never run in a loop without explicit scheduling
- Never suppress the confirmation prompt when `--apply` is active
- Never commit `testbed.yaml`, `src_env`, or any file containing credentials
- Never ignore pyATS connection errors silently — fail loudly
- Never assume a device exists in Netbox — always check first and fail with a clear message
