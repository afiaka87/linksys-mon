# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "python-dotenv",
#     "pydantic",
#     "requests",
# ]
#
# ///

import argparse
import base64
from datetime import datetime
from functools import lru_cache
from typing import List, Optional, Set
from uuid import UUID
import os

import requests
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

# Environment variables
LINKSYS_USERNAME = os.environ["LINKSYS_USERNAME"]
LINKSYS_PASSWORD = os.environ["LINKSYS_PASSWORD"]

# Constants
BASE_URL = "http://192.168.1.1/JNAP/"
AUTH = base64.b64encode(f"{LINKSYS_USERNAME}:{LINKSYS_PASSWORD}".encode()).decode()
HEADERS = {
    "X-JNAP-Authorization": f"Basic {AUTH}",
}


class Model(BaseModel):
    deviceType: str
    manufacturer: Optional[str] = None
    modelNumber: Optional[str] = None
    hardwareVersion: Optional[str] = None
    description: Optional[str] = None


class Unit(BaseModel):
    serialNumber: Optional[str] = None
    firmwareVersion: Optional[str] = None
    firmwareDate: Optional[datetime] = None


class Interface(BaseModel):
    macAddress: str
    interfaceType: str
    band: Optional[str] = None


class Connection(BaseModel):
    macAddress: str
    ipAddress: Optional[str] = None
    ipv6Address: Optional[str] = None
    parentDeviceID: Optional[UUID] = None


class Property(BaseModel):
    name: str
    value: str


class Device(BaseModel):
    deviceID: UUID
    lastChangeRevision: int
    model: Model
    unit: Unit
    isAuthority: bool
    nodeType: Optional[str] = None
    friendlyName: Optional[str] = None
    knownInterfaces: List[Interface]
    connections: List[Connection]
    properties: List[Property]
    maxAllowedProperties: int


class DeviceStatus(BaseModel):
    device: Device
    is_online: bool
    online_interfaces: List[Interface]


def fetch_api_data(action: str, data: str = "{}") -> dict:
    """Generic API call function"""
    return requests.post(
        BASE_URL,
        headers={"X-JNAP-Action": action, **HEADERS},
        data=data,
    ).json()


@lru_cache()
def get_devices() -> List[Device]:
    """Fetch and parse all known devices"""
    response = fetch_api_data(
        "http://linksys.com/jnap/core/Transaction",
        '[{"action":"http://linksys.com/jnap/devicelist/GetDevices3","request":{"sinceRevision":0}}]',
    )

    def parse_device(device: dict) -> Device:
        device_data = device.copy()
        device_data.update(
            {
                "model": Model(**device["model"]),
                "unit": Unit(**device["unit"]),
                "knownInterfaces": [Interface(**i) for i in device["knownInterfaces"]],
                "connections": [Connection(**c) for c in device["connections"]],
                "properties": [Property(**p) for p in device["properties"]],
            }
        )
        return Device(**device_data)

    return [parse_device(d) for d in response["responses"][0]["output"]["devices"]]


def get_online_macs() -> Set[str]:
    """Get set of currently online MAC addresses"""
    response = fetch_api_data(
        "http://linksys.com/jnap/nodes/networkconnections/GetNodesWirelessNetworkConnections"
    )
    return {
        conn["macAddress"]
        for device in response["output"]["nodeWirelessConnections"]
        for conn in device["connections"]
    }


def filter_devices(
    devices: List[Device], *, friendly_name: str = None, mac_address: str = None
) -> List[Device]:
    """Filter devices based on friendly name or MAC address"""
    if friendly_name:
        devices = [
            d
            for d in devices
            if friendly_name.lower() in (d.friendlyName or "").lower()
        ]
    if mac_address:
        mac_address = mac_address.upper()
        devices = [
            d
            for d in devices
            if any(i.macAddress == mac_address for i in d.knownInterfaces)
        ]
    return devices


def get_device_status(device: Device, online_macs: Set[str]) -> DeviceStatus:
    """Get online status for a single device"""
    online_interfaces = [
        i for i in device.knownInterfaces if i.macAddress in online_macs
    ]
    return DeviceStatus(
        device=device,
        is_online=bool(online_interfaces),
        online_interfaces=online_interfaces,
    )


def print_online_devices(devices: List[DeviceStatus]):
    """Print online devices in a formatted way"""
    print("\n🌐 Currently Connected Devices")
    print("=" * 70)
    for status in devices:
        name = status.device.friendlyName or "Unknown Device"
        macs = ", ".join(i.macAddress for i in status.online_interfaces)
        macs = f"{macs[:22]}..." if len(macs) > 25 else macs
        name_padded = f"{name}{' ' * max(0, 30 - len(name))}"
        print(f"✓ {name_padded} │ {macs}")


def print_offline_devices(devices: List[DeviceStatus]):
    """Print offline devices in columns"""
    print(f"\n💤 Offline Devices ({len(devices)} total)")
    print("=" * 70)
    COLUMN_WIDTH = 35
    for i in range(0, len(devices), 2):
        row = ""
        for device in devices[i : i + 2]:
            name = device.device.friendlyName or "Unknown Device"
            name = (
                f"{name[: COLUMN_WIDTH - 8]}..."
                if len(name) > COLUMN_WIDTH - 5
                else name
            )
            row += f"✗ {name:<{COLUMN_WIDTH}}"
        print(row)


def main():
    parser = argparse.ArgumentParser(
        description="Display device connection status from Linksys router"
    )
    parser.add_argument(
        "--online", action="store_true", help="Show only online devices"
    )
    parser.add_argument(
        "--offline", action="store_true", help="Show only offline devices"
    )
    parser.add_argument("--friendly", type=str, help="Filter devices by friendly name")
    parser.add_argument("--mac", type=str, help="Filter devices by MAC address")
    args = parser.parse_args()

    # Get and filter devices
    devices = [
        d
        for d in get_devices()
        if not (len(d.friendlyName or "") == 36 and "-" in (d.friendlyName or ""))
    ]
    devices = filter_devices(devices, friendly_name=args.friendly, mac_address=args.mac)

    # Get online status for all devices
    online_macs = get_online_macs()
    device_statuses = [get_device_status(d, online_macs) for d in devices]

    # Split into online/offline
    online = [s for s in device_statuses if s.is_online]
    offline = [s for s in device_statuses if not s.is_online]

    # Display results based on flags
    if not args.offline or args.online:
        print_online_devices(online)
    if not args.online or args.offline:
        print_offline_devices(offline)
    if not args.online and not args.offline:
        filter_msg = (
            f" matching {'friendly name' if args.friendly else 'MAC'} '{args.friendly or args.mac}'"
            if (args.friendly or args.mac)
            else ""
        )
        print(
            f"\nTotal Devices{filter_msg}: {len(devices)} (🌐 {len(online)} online, 💤 {len(offline)} offline)"
        )


if __name__ == "__main__":
    main()
