#!/usr/bin/env python3
"""Terminal client for Perific Energy Meter - reads all available data."""

import asyncio
import getpass
import sys
from datetime import datetime, timezone

from perific.client import Client, AuthenticationError
from const import API_URL


def fmt_ts(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def print_packet(label: str, packet):
    if packet is None:
        print(f"  {label}: no data")
        return
    d = packet.data
    print(f"  {label} (ts={fmt_ts(packet.ts)}, fw={packet.fw}, rssi={packet.rssi} dBm):")
    # Voltage
    uavg = d.uavg or []
    huavg = d.huavg or []
    for i, phase in enumerate(["L1", "L2", "L3"]):
        v = uavg[i] if i < len(uavg) else None
        hv = huavg[i] if i < len(huavg) else None
        if v is not None:
            note = f"  (peak {hv:.1f} V)" if hv is not None else ""
            print(f"    Voltage {phase}: {v:.1f} V{note}")
    # Current
    iavg = d.iavg or []
    hiavg = d.hiavg or []
    for i, phase in enumerate(["L1", "L2", "L3"]):
        c = iavg[i] if i < len(iavg) else None
        hc = hiavg[i] if i < len(hiavg) else None
        if c is not None:
            note = f"  (peak {hc:.2f} A)" if hc is not None else ""
            print(f"    Current {phase}: {c:.2f} A{note}")
    # Power per phase (V * I)
    total_power = 0.0
    for i, phase in enumerate(["L1", "L2", "L3"]):
        v = uavg[i] if i < len(uavg) else None
        c = iavg[i] if i < len(iavg) else None
        if v is not None and c is not None:
            p = v * c / 1000
            total_power += p
            print(f"    Power   {phase}: {p:.3f} kW")
    if total_power:
        print(f"    Power Total: {total_power:.3f} kW")
    # Energy
    if d.hwi is not None:
        print(f"    Energy Total: {d.hwi:.3f} kWh")


async def main():
    print("=== Perific Energy Meter Terminal Client ===\n")

    username = input("Username: ").strip()
    password = getpass.getpass("Password: ")

    client = Client(API_URL)

    print("\nAuthenticating...")
    try:
        token = await client.authenticate(username, password)
    except AuthenticationError:
        print("Authentication failed: invalid credentials.")
        sys.exit(1)
    except Exception as e:
        print(f"Authentication error: {e}")
        sys.exit(1)

    print(f"Token valid until: {token.valid_to}\n")

    # Devices
    print("Fetching account overview...")
    try:
        overview = await client.getAccountOverview(token.token)
    except AuthenticationError:
        print("Unauthorized — token rejected.")
        sys.exit(1)
    except Exception as e:
        print(f"Error fetching account overview: {e}")
        sys.exit(1)

    items = overview.items
    if not items:
        print("No devices found on this account.")
        sys.exit(0)

    print(f"Found {len(items)} device(s):\n")
    for item in items:
        print(f"  Device: {item.name}")
        print(f"    ID:        {item.id}")
        print(f"    MAC:       {item.mac_address}")
        print(f"    Category:  {item.item_category}")
        print(f"    Type:      {item.item_type} / {item.item_sub_type}")
        if item.system_name:
            print(f"    System:    {item.system_name}")
        print(f"    Timezone:  {item.time_zone}")
        print(f"    Created:   {item.creation_time}")

    # Latest packets
    print("\nFetching latest sensor packets...")
    try:
        all_packets = await client.getLatestPackets(token.token)
    except AuthenticationError:
        print("Unauthorized — token rejected.")
        sys.exit(1)
    except Exception as e:
        print(f"Error fetching packets: {e}")
        sys.exit(1)

    # Build device name lookup
    name_by_id = {item.id: item.name for item in items}

    print(f"\n{'=' * 50}")
    for lip in all_packets:
        name = name_by_id.get(lip.item_id, f"Device {lip.item_id}")
        print(f"\nDevice: {name} (ID={lip.item_id})")
        lp = lip.latest_packets
        print_packet("Real-Time", lp.phase_real_time)
        print_packet("Minute",    lp.phase_minute)
        print_packet("Hour",      lp.phase_hour)
        print_packet("Day",       lp.phase_day)
    print(f"\n{'=' * 50}")


if __name__ == "__main__":
    asyncio.run(main())
