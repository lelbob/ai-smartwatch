"""
restore_and_dump.py - Restores original USB Composite + Coolsand serial drivers,
then uses COM port DIAG protocol to read NOR flash memory.

All software - no hardware manipulation needed.
"""

import subprocess
import time
import os
import sys

def run_ps(cmd):
    """Run a PowerShell command and return output."""
    res = subprocess.run(["powershell", "-Command", cmd], capture_output=True, text=True)
    return res.stdout.strip(), res.stderr.strip()

def get_1782_devices():
    """Get all 1782 PnP devices."""
    out, _ = run_ps('Get-PnpDevice | Where-Object { $_.InstanceId -like "*1782*" } | Select-Object FriendlyName, InstanceId, Status, Class | ConvertTo-Json')
    import json
    try:
        devs = json.loads(out)
        if isinstance(devs, dict):
            devs = [devs]
        return devs
    except:
        return []

def main():
    print("=" * 60)
    print("   RESTORE COM PORTS & DUMP FLASH VIA DIAG SERIAL")
    print("=" * 60)
    
    # Step 1: Show current device state
    print("\n[Step 1] Current device state:")
    devs = get_1782_devices()
    for d in devs:
        status = d.get("Status", "?")
        cls = d.get("Class", "?") 
        name = d.get("FriendlyName", "?")
        iid = d.get("InstanceId", "?")
        print(f"  {name:30s} | {status:10s} | {str(cls):20s} | {iid}")
    
    # Step 2: Find and remove libusbK driver
    print("\n[Step 2] Removing libusbK driver package...")
    out, _ = run_ps('pnputil /enum-drivers | Select-String -Pattern "libusbK" -Context 5')
    print(f"  libusbK driver search: {out[:200] if out else 'not found'}")
    
    # Find the OEM inf for libusbK
    out, _ = run_ps('pnputil /enum-drivers')
    lines = out.split('\n')
    oem_inf = None
    for i, line in enumerate(lines):
        if 'libusbK' in line or 'libusb' in line.lower():
            # Look backwards for the Published Name line
            for j in range(max(0, i-10), i):
                if 'Published Name' in lines[j] or 'Published name' in lines[j]:
                    oem_inf = lines[j].split(':')[-1].strip()
                    break
    
    if oem_inf:
        print(f"  Found libusbK driver: {oem_inf}")
        print(f"  Attempting to delete {oem_inf}...")
        out, err = run_ps(f'pnputil /delete-driver {oem_inf} /force')
        print(f"  Result: {out} {err}")
    else:
        print("  libusbK driver package not found in pnputil.")
    
    # Step 3: Force re-enumerate the parent USB device to get composite driver back
    print("\n[Step 3] Re-enumerating USB devices...")
    parent_iid = None
    for d in devs:
        iid = d.get("InstanceId", "")
        if "MI_" not in iid and "1782" in iid and "3D00" in iid:
            parent_iid = iid
            break
    
    if parent_iid:
        print(f"  Parent device: {parent_iid}")
        # Disable and re-enable to force driver re-binding
        out, err = run_ps(f'pnputil /restart-device "{parent_iid}"')
        print(f"  Restart result: {out} {err}")
    
    # Also scan for new devices
    out, _ = run_ps('pnputil /scan-devices')
    print(f"  Scan: {out}")
    
    time.sleep(3)
    
    # Step 4: Check if COM ports came back
    print("\n[Step 4] Checking for COM ports...")
    try:
        import serial.tools.list_ports
        ports = list(serial.tools.list_ports.comports())
        print(f"  Available COM ports: {len(ports)}")
        for p in ports:
            print(f"    {p.device}: {p.description} [{p.hwid}]")
    except Exception as e:
        print(f"  Error listing ports: {e}")
    
    # Also check PnP state
    print("\n[Step 5] Updated device state:")
    devs = get_1782_devices()
    for d in devs:
        status = d.get("Status", "?")
        cls = d.get("Class", "?")
        name = d.get("FriendlyName", "?")
        iid = d.get("InstanceId", "?")
        present = "ACTIVE" if status == "OK" else status
        print(f"  {name:30s} | {present:10s} | {str(cls):20s}")
    
    # Step 6: Try to open any available COM ports and send DIAG commands
    print("\n[Step 6] Attempting DIAG communication on available COM ports...")
    import serial
    import struct
    
    def sprd_crc16(data):
        crc = 0
        for b in data:
            crc ^= b
            for _ in range(8):
                if crc & 1:
                    crc = (crc >> 1) ^ 0x8408
                else:
                    crc >>= 1
        return crc & 0xFFFF
    
    def build_hdlc(cmd_id, sub_cmd=0, payload=b""):
        raw = bytes([cmd_id, sub_cmd]) + payload
        crc = sprd_crc16(raw)
        packet = raw + struct.pack("<H", crc)
        stuffed = bytearray()
        for b in packet:
            if b == 0x7E:
                stuffed.extend([0x7D, 0x5E])
            elif b == 0x7D:
                stuffed.extend([0x7D, 0x5D])
            else:
                stuffed.append(b)
        return bytes([0x7E]) + bytes(stuffed) + bytes([0x7E])
    
    # Try all possible COM port numbers
    test_ports = []
    try:
        test_ports = [p.device for p in serial.tools.list_ports.comports()]
    except:
        pass
    
    # Also try common Coolsand ports
    for p in ["COM3", "COM4", "COM5", "COM6", "COM7", "COM8"]:
        if p not in test_ports:
            test_ports.append(p)
    
    for port in test_ports:
        for baud in [921600, 115200]:
            try:
                ser = serial.Serial(port, baudrate=baud, timeout=1, write_timeout=1)
                print(f"\n  [OPENED] {port} @ {baud} baud")
                
                # Try passive read first
                ser.reset_input_buffer()
                time.sleep(0.2)
                passive = ser.read(256)
                if passive:
                    print(f"    Passive data: {passive[:60]}")
                
                # Try DIAG commands
                for label, frame in [
                    ("PING", build_hdlc(0x00, 0x00)),
                    ("GET_VERSION", build_hdlc(0x0F, 0x00)),
                    ("READ_NV_1", build_hdlc(0x05, 0x00, struct.pack("<H", 1))),
                    ("READ_FLASH", build_hdlc(0x11, 0x00, struct.pack("<II", 0x80000000, 256))),
                    ("READ_MEM", build_hdlc(0x13, 0x00, struct.pack("<II", 0x80000000, 256))),
                ]:
                    ser.reset_input_buffer()
                    ser.write(frame)
                    time.sleep(0.3)
                    resp = ser.read(1024)
                    if resp:
                        is_debug = b"is_gprs" in resp or b"wifi_" in resp
                        if not is_debug:
                            print(f"    {label}: *** BINARY RESPONSE *** ({len(resp)} bytes): {resp[:32].hex()}")
                        else:
                            print(f"    {label}: debug log ({len(resp)} bytes)")
                    else:
                        print(f"    {label}: no response")
                
                ser.close()
            except Exception as e:
                if "FileNotFoundError" not in str(e) and "PermissionError" not in str(e):
                    print(f"  {port}@{baud}: {e}")

if __name__ == "__main__":
    main()
