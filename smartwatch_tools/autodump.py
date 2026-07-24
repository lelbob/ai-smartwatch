import subprocess
import usb.core
import usb.backend.libusb1
import time
import struct
import os

SPD_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "spd_dump"))
FDL1 = os.path.join(SPD_DIR, "t117_fdl1.bin")
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

def trigger_soft_reset_usb():
    print("Sending USB Mode Switch reset packet over libusbK...")
    try:
        dll_path = os.path.join(SPD_DIR, "libusb-1.0.dll")
        backend = usb.backend.libusb1.get_backend(find_library=lambda x: dll_path)
        dev = usb.core.find(idVendor=0x1782, idProduct=0x3D00, backend=backend)
        if dev is not None:
            frame = build_hdlc_frame(0x0A, 0x01)
            try:
                dev.write(0x02, frame, timeout=200)
                print("[OK] Soft reset packet sent successfully to EP 0x02.")
            except Exception as e:
                print(f"[INFO] Write note: {e}")
    except Exception as e:
        print(f"[INFO] USB soft reset exception: {e}")

def run_executable(exe_name):
    exe_path = os.path.join(SPD_DIR, exe_name)
    if not os.path.exists(exe_path):
        return False
    print(f"\n---> Running {exe_name}...")
    cmd = [
        exe_path,
        "--verbose", "2",
        "--wait", "5",
        "fdl", FDL1, "0x40004000",
        "read_flash", "0x80000000", "0", "16M", OUT_BIN
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, cwd=SPD_DIR)
    print("STDOUT:", res.stdout.strip())
    print("STDERR:", res.stderr.strip())
    if os.path.exists(OUT_BIN) and os.path.getsize(OUT_BIN) > 0:
        print(f"[SUCCESS] Flash binary downloaded to {OUT_BIN} ({os.path.getsize(OUT_BIN)} bytes)!")
        return True
    return False

def main():
    print("=" * 60)
    print("      UNISOC SC6531 Multi-Profile Flash Dumper      ")
    print("=" * 60)
    
    trigger_soft_reset_usb()
    time.sleep(0.5)
    
    for exe in ["spd_dump.exe", "spd_dump_3d00.exe", "spd_dump_ep2.exe"]:
        if run_executable(exe):
            break

if __name__ == "__main__":
    main()
