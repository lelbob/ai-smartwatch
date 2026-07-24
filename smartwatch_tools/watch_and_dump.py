import subprocess
import os
import sys
import time
import struct
import usb.core
import usb.backend.libusb1

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
    crc_bytes = struct.pack("<H", crc)
    packet = raw + crc_bytes
    
    stuffed = bytearray()
    for b in packet:
        if b == 0x7E:
            stuffed.extend([0x7D, 0x5E])
        elif b == 0x7D:
            stuffed.extend([0x7D, 0x5D])
        else:
            stuffed.append(b)
            
    return bytes([0x7E]) + bytes(stuffed) + bytes([0x7E])

def send_soft_reset(dev):
    print("Sending Mode Switch reboot frame to trigger BootROM (PID 0x4D00)...")
    frame = build_hdlc_frame(0x0A, 0x01)
    for ep in [0x02, 0x03]:
        try:
            dev.write(ep, frame, timeout=200)
            print(f"  [OK] Sent mode switch to EP {hex(ep)}")
        except Exception:
            pass

def main():
    print("=" * 60)
    print("   AUTOMATED UNISOC SMARTWATCH FIRMWARE CAPTURE MONITOR   ")
    print("=" * 60)
    print("\nScanning USB for UNISOC SC6531 device...")
    
    dll_path = os.path.join(SPD_DIR, "libusb-1.0.dll")
    backend = usb.backend.libusb1.get_backend(find_library=lambda x: dll_path)
    
    dev_3d00 = usb.core.find(idVendor=0x1782, idProduct=0x3D00, backend=backend)
    dev_4d00 = usb.core.find(idVendor=0x1782, idProduct=0x4D00, backend=backend)
    
    if dev_4d00 is not None:
        print("[DETECTED] Device is already in BootROM Mode (PID 0x4D00)!")
    elif dev_3d00 is not None:
        print("[DETECTED] Device is in Active OS Mode (PID 0x3D00).")
        send_soft_reset(dev_3d00)
        time.sleep(1.5)
    else:
        print("[INFO] Device not detected yet.")
        return

    print("\nLaunching spd_dump to catch BootROM handshaking...")
    cmd = [SPD_DUMP, "--wait", "10", "fdl", FDL_T117, "0x40004000", "read_flash", "0x80000000", "0", "16M", OUT_BIN]
    print(f"Executing: {' '.join(cmd)}")
    res = subprocess.run(cmd, capture_output=True, text=True, cwd=SPD_DIR)
    
    print("\n--- STDOUT ---")
    print(res.stdout)
    print("\n--- STDERR ---")
    print(res.stderr)
    
    if os.path.exists(OUT_BIN) and os.path.getsize(OUT_BIN) > 0:
        print(f"\n[SUCCESS] Firmware dumped to {OUT_BIN} ({os.path.getsize(OUT_BIN)} bytes)!")

if __name__ == "__main__":
    main()
