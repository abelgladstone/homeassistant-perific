#!/usr/bin/env python3
"""Terminal client for Perific Energy Meter - reads all available data."""

import argparse
import asyncio
import getpass
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv, set_key
from perific.client import Client, AuthenticationError
from const import API_URL

ENV_FILE = Path(__file__).parent / ".env"


def fmt_ts(ts: int) -> str:
    return datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


PHASES = ["L1", "L2", "L3"]


def print_packet(label: str, packet):
    if packet is None:
        print(f"  {label}: no data")
        return
    d = packet.data
    print(f"  {label} (ts={fmt_ts(packet.ts)}, fw={packet.fw}, rssi={packet.rssi} dBm):")

    huavg = d.huavg or []
    hiavg = d.hiavg or []
    himin = d.himin or []
    himax = d.himax or []

    # Voltage
    for i, phase in enumerate(PHASES):
        v = huavg[i] if i < len(huavg) else None
        if v is not None:
            print(f"    Voltage {phase}:  {v:.1f} V")

    # Current + power per phase
    total_import_w = 0.0
    total_export_w = 0.0
    for i, phase in enumerate(PHASES):
        v = huavg[i] if i < len(huavg) else None
        c = hiavg[i] if i < len(hiavg) else None
        lo = himin[i] if i < len(himin) else None
        hi = himax[i] if i < len(himax) else None
        if c is not None:
            bounds = ""
            if lo is not None and hi is not None:
                bounds = f"  (min {lo:.2f} / max {hi:.2f} A)"
            print(f"    Current {phase}: {c:.2f} A{bounds}")
        if v is not None and c is not None:
            w = v * c / 1000  # kW
            if w >= 0:
                total_import_w += w
                print(f"    Power   {phase}: {w:.3f} kW (import)")
            else:
                total_export_w += abs(w)
                print(f"    Power   {phase}: {abs(w):.3f} kW (export)")

    if total_import_w or total_export_w:
        print(f"    Power Total: import {total_import_w:.3f} kW / export {total_export_w:.3f} kW")

    # Per-phase energy (hour/day packets)
    hwpi = d.hwpi or []
    hwpo = d.hwpo or []
    for i, phase in enumerate(PHASES):
        pi = hwpi[i] if i < len(hwpi) else None
        po = hwpo[i] if i < len(hwpo) else None
        if pi is not None or po is not None:
            parts = []
            if pi is not None:
                parts.append(f"import {pi:.3f} kWh")
            if po is not None:
                parts.append(f"export {po:.3f} kWh")
            print(f"    Energy  {phase}: {' / '.join(parts)}")

    # Energy totals
    if d.hwi is not None:
        print(f"    Energy Import Total: {d.hwi:.3f} kWh")
    if d.hwo is not None:
        print(f"    Energy Export Total: {d.hwo:.3f} kWh")


async def main():
    load_dotenv(ENV_FILE)

    parser = argparse.ArgumentParser(description="Perific Energy Meter Terminal Client")
    parser.add_argument("-u", "--username", default=os.environ.get("PERIFIC_USERNAME"), help="Account username (or set PERIFIC_USERNAME)")
    parser.add_argument("-p", "--password", default=os.environ.get("PERIFIC_PASSWORD"), help="Account password (or set PERIFIC_PASSWORD)")
    args = parser.parse_args()

    print("=== Perific Energy Meter Terminal Client ===\n")

    prompted = False
    username = args.username
    password = args.password

    if not username:
        username = input("Username: ").strip()
        prompted = True
    if not password:
        password = getpass.getpass("Password: ")
        prompted = True

    if prompted:
        save = input("Save credentials to .env for next time? [y/N]: ").strip().lower()
        if save == "y":
            set_key(ENV_FILE, "PERIFIC_USERNAME", username)
            set_key(ENV_FILE, "PERIFIC_PASSWORD", password)
            print(f"Credentials saved to {ENV_FILE}\n")

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
