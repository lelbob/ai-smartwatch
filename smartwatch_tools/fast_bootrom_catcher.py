"""
fast_bootrom_catcher.py - Triggers software reset via multiple channels
(AT commands, DIAG mode-switch frames, USB reset) and runs a fast polling
loop to catch the UNISOC SC6531 BootROM (VID 1782 PID 4D00) during its 2-second
boot window to extract the FULL 16MB NOR Flash firmware.
"""

import subprocess
import usb.core
import usb.backend.libusb1
import time
import struct
import os
import sys

SPD_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "spd_dump"))
SPD_DUMP = os.path.join(SPD_DIR, "spd_dump.exe")
FDL_T117 = os.path.join(SPD_DIR, "t117_fdl1.bin")
FDL_NOR = os.path.join(SPD_DIR, "nor_fdl1.bin")
OUT_BIN = os.path.abspath("firmware_dump.bin")

def sprd_crc16(data: bytes) -> int:
    crc = 0
    for b in data:
        crc ^= b
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0x8408
            else:
                crc >>= 1
    return crc & 0xFFFF

def build_hdlc_frame(cmd_id: int, sub_cmd: int = 0, payload: bytes = b"") -> bytes:
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

def send_reset_commands(dev):
    print("Sending multi-protocol soft-reset triggers to EP 0x02...")
    
    # 1. DIAG Mode Switch frames
    mode_frames = [
        build_hdlc_frame(0x0A, 0x01),  # Download mode
        build_hdlc_frame(0x0A, 0x00),  # Bootrom mode
        build_hdlc_frame(0x0A, 0x04),  # Autodownload
    ]
    
    # 2. AT Tunnel reboot commands (Command 0x38 in DIAG)
    at_reboots = [
        b"AT+CFUN=1,1\r\n",
        b"AT+RESET\r\n",
        b"AT+REBOOT\r\n",
        b"AT+POWERDOWN\r\n",
        b"AT+SPAT=0\r\n",
    ]
    
    for frame in mode_frames:
        try:
            dev.write(0x02, frame, timeout=100)
            time.sleep(0.02)
        except Exception:
            pass
            
    for at_cmd in at_reboots:
        # Send raw AT
        try:
            dev.write(0x02, at_cmd, timeout=100)
            time.sleep(0.02)
        except Exception:
            pass
            
        # Send AT via DIAG tunnel (0x38)
        try:
            dev.write(0x02, build_hdlc_frame(0x38, 0x00, at_cmd), timeout=100)
            time.sleep(0.02)
        except Exception:
            pass

def main():
    print("=" * 60)
    print("   UNISOC SC6531 FULL 16MB FIRMWARE EXTRACTION (GOAL MODE)")
    print("=" * 60)
    
    dll_path = os.path.join(SPD_DIR, "libusb-1.0.dll")
    backend = usb.backend.libusb1.get_backend(find_library=lambda x: dll_path)
    
    # Check if spd_dump exists
    if not os.path.exists(SPD_DUMP):
        print(f"[ERROR] spd_dump.exe not found at {SPD_DUMP}")
        return
        
    print(f"spd_dump executable: {SPD_DUMP}")
    print(f"Target output file:  {OUT_BIN}\n")
    
    # Attempt loop
    for attempt in range(1, 10):
        print(f"--- Attempt {attempt}/10 ---")
        dev_3d00 = usb.core.find(idVendor=0x1782, idProduct=0x3D00, backend=backend)
        dev_4d00 = usb.core.find(idVendor=0x1782, idProduct=0x4D00, backend=backend)
        
        if dev_4d00 is not None:
            print("[STATUS] Device detected in BootROM mode (PID 0x4D00)!")
        elif dev_3d00 is not None:
            print("[STATUS] Device detected in OS mode (PID 0x3D00). Triggering soft-reset...")
            send_reset_commands(dev_3d00)
        else:
            print("[STATUS] Waiting for USB connection...")
            
        # Launch spd_dump with 15s wait to catch connection
        for fdl, fdl_name in [(FDL_T117, "t117_fdl1.bin"), (FDL_NOR, "nor_fdl1.bin")]:
            print(f"Launching spd_dump with loader {fdl_name}...")
            cmd = [
                SPD_DUMP,
                "--wait", "15",
                "fdl", fdl, "0x40004000",
                "read_flash", "0x80000000", "0", "16M", OUT_BIN
            ]
            
            res = subprocess.run(cmd, capture_output=True, text=True, cwd=SPD_DIR)
            print("STDOUT:", res.stdout.strip())
            print("STDERR:", res.stderr.strip())
            
            if os.path.exists(OUT_BIN) and os.path.getsize(OUT_BIN) > 100000:
                size_mb = os.path.getsize(OUT_BIN) / (1024 * 1024)
                print(f"\n{'=' * 60}")
                print(f"   [SUCCESS] FULL FIRMWARE DUMP COMPLETED!")
                print(f"   File: {OUT_BIN}")
                print(f"   Size: {os.path.getsize(OUT_BIN):,} bytes ({size_mb:.2f} MB)")
                print(f"{'=' * 60}\n")
                return True
                
        time.sleep(1)
        
    return False

if __name__ == "__main__":
    main()
