"""
watch_usb.py - Monitors USB device changes in real time to capture the exact
VID/PID when the watch is plugged in during "charging mode" (second button held).
Run this script FIRST, then plug in the watch with the button held.
"""

import subprocess
import time
import ctypes
import sys

def get_usb_devices():
    """Get current USB device list via pnputil"""
    result = subprocess.run(
        ["powershell", "-Command",
         "Get-PnpDevice -PresentOnly | Where-Object DeviceID -like '*USB*VID*' | Select-Object FriendlyName, DeviceID, Status | ConvertTo-Json"],
        capture_output=True, text=True
    )
    devices = {}
    try:
        import json
        data = json.loads(result.stdout)
        if isinstance(data, dict):
            data = [data]
        for dev in data:
            did = dev.get("DeviceID", "")
            fname = dev.get("FriendlyName", "Unknown")
            status = dev.get("Status", "")
            devices[did] = (fname, status)
    except Exception:
        pass
    return devices

def main():
    print("=" * 60)
    print("   USB DEVICE MONITOR - Watching for watch connection...")
    print("=" * 60)
    print()
    print("INSTRUCTIONS:")
    print("  1. Make sure the watch is UNPLUGGED right now.")
    print("  2. Turn the watch completely OFF.")
    print("  3. Press and HOLD the SECOND (non-power) button on the watch.")
    print("  4. While holding it, plug the USB cable into the PC.")
    print("  5. This script will instantly capture what VID/PID appears.")
    print()
    print("Monitoring USB changes (press Ctrl+C to stop)...")
    print()

    baseline = get_usb_devices()
    print(f"Baseline: {len(baseline)} USB devices detected.")
    
    while True:
        time.sleep(0.3)
        current = get_usb_devices()
        
        # Find new devices
        for did, (fname, status) in current.items():
            if did not in baseline:
                print()
                print("=" * 60)
                print("  >>> NEW DEVICE DETECTED! <<<")
                print(f"  Name:      {fname}")
                print(f"  Device ID: {did}")
                print(f"  Status:    {status}")
                print("=" * 60)
                
        # Find removed devices
        for did, (fname, status) in baseline.items():
            if did not in current:
                print(f"  [REMOVED] {fname} ({did})")
                
        baseline = current

if __name__ == "__main__":
    main()
