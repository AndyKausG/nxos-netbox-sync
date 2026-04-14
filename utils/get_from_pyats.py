"""
utils/get_from_pyats.py — pyATS/Genie helpers (platform-aware, IOS/IOS-XE + NX-OS).

All functions take an explicit `device` object rather than relying on module-level state.
Use connect(device_name) to load testbed.yaml and return a connected device.
"""
from genie.testbed import load as load_testbed
from genie.libs.conf.vlan import Vlan
from genie.libs.conf.interface import Interface


def connect(device_name):
    """Load testbed.yaml and return a connected device object."""
    testbed = load_testbed("testbed.yaml")
    if device_name not in testbed.devices:
        raise KeyError(f"Device '{device_name}' not found in testbed.yaml")
    device = testbed.devices[device_name]
    device.connect(learn_hostname=True, log_stdout=False)
    return device


def platform_info(device):
    return device.learn("platform")


def interfaces_current(device):
    interfaces = device.learn("interface")
    return interfaces.info


def vlans_current(device):
    vlans = device.learn("vlan").info["vlans"]
    return vlans


def vlans_configure(device, netbox_vlans):
    results = []
    for vlan in netbox_vlans:
        print(f"  Creating VLAN {vlan.vid} ({vlan.name})")
        new_vlan = Vlan(vlan_id=str(vlan.vid), name=vlan.name)
        device.add_feature(new_vlan)
        output = new_vlan.build_config()
        results.append({vlan.name: output})
    return results


def vlans_remove(device, netbox_vlans):
    results = []
    for vlan in netbox_vlans:
        print(f"  Removing VLAN {vlan.vid} ({vlan.name})")
        new_vlan = Vlan(vlan_id=vlan.vid, name=vlan.name)
        device.add_feature(new_vlan)
        output = new_vlan.build_unconfig()
        results.append({vlan.name: output})
    return results


def interface_enable_state_configure(device, netbox_interfaces):
    results = []
    for interface in netbox_interfaces:
        print(f"  Setting {interface.name} enabled → {interface.enabled}")
        if interface.name in device.interfaces:
            new_interface = device.interfaces[interface.name]
        else:
            new_interface = Interface(name=interface.name, device=device)
        new_interface.enabled = interface.enabled
        output = new_interface.build_config()
        results.append(output)
    return results


def interface_description_configure(device, netbox_interfaces):
    results = []
    for interface in netbox_interfaces:
        print(f"  Setting {interface.name} description → '{interface.description}'")
        if interface.name in device.interfaces:
            new_interface = device.interfaces[interface.name]
        else:
            new_interface = Interface(name=interface.name, device=device)
        if interface.description in ("", " ", None):
            output = new_interface.build_unconfig(attributes={"description": None}, apply=False)
        else:
            new_interface.description = interface.description
            output = new_interface.build_config()
        results.append(output)
    return results


def interface_switchport_configure(device, netbox_interfaces):
    results = []
    for interface in netbox_interfaces:
        print(f"  Updating {interface.name} switchport mode → {interface.mode}")
        if interface.mode.label in ("Tagged", "Tagged All"):
            new_interface = _interface_trunk_configure(device, interface)
        elif interface.mode.label == "Access":
            new_interface = _interface_access_configure(device, interface)
        else:
            print(f"  Unknown switchport mode for {interface.name}: {interface.mode.label}")
            continue
        if new_interface:
            output = new_interface.build_config()
            results.append(output)
    return results


def _interface_trunk_configure(device, netbox_interface):
    if netbox_interface.mode.label not in ("Tagged", "Tagged All"):
        print(f"  {netbox_interface.name} is not a trunk interface")
        return False
    if netbox_interface.name in device.interfaces:
        new_interface = device.interfaces[netbox_interface.name]
    else:
        new_interface = Interface(name=netbox_interface.name, device=device)
    new_interface.switchport_enable = True
    new_interface.switchport_mode = "trunk"
    if netbox_interface.untagged_vlan:
        new_interface.native_vlan = str(netbox_interface.untagged_vlan.vid)
    if netbox_interface.tagged_vlans:
        vlan_list = [str(vlan.vid) for vlan in netbox_interface.tagged_vlans]
        new_interface.trunk_vlans = ",".join(vlan_list)
    if netbox_interface.mode.label == "Tagged All":
        new_interface.trunk_add_vlans = "1-4094"
    return new_interface


def _interface_access_configure(device, netbox_interface):
    if netbox_interface.mode.label != "Access":
        print(f"  {netbox_interface.name} is not an access interface")
        return False
    if netbox_interface.name in device.interfaces:
        new_interface = device.interfaces[netbox_interface.name]
    else:
        new_interface = Interface(name=netbox_interface.name, device=device)
    new_interface.switchport_enable = True
    new_interface.switchport_mode = "access"
    new_interface.access_vlan = str(netbox_interface.untagged_vlan.vid)
    return new_interface
