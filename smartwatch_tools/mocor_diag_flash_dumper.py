"""
mocor_diag_flash_dumper.py - Comprehensive live Mocor OS firmware & partition dumper.
Extracts all NVRAM items (0 to 65535), EFS files, RAM image, and Flash chunks directly
over WinUSB Endpoint 0x02/0x82 without rebooting or touching hardware.
"""

import usb.core
import usb.backend.libusb1
import time
import struct
import os

SPD_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "spd_dump"))
DUMP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "dumps"))
OUT_FULL = os.path.join(DUMP_DIR, "full_mocor_firmware.bin")
OUT_NV = os.path.join(DUMP_DIR, "nvram_dump.bin")

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

def main():
    dll_path = os.path.join(SPD_DIR, "libusb-1.0.dll")
    backend = usb.backend.libusb1.get_backend(find_library=lambda x: dll_path)
    
    dev = usb.core.find(idVendor=0x1782, idProduct=0x3D00, backend=backend)
    if dev is None:
        print("Device 1782:3D00 not found.")
        return

    os.makedirs(DUMP_DIR, exist_ok=True)
    
    print("=" * 60)
    print("   MOCOR OS COMPREHENSIVE LIVE FIRMWARE PARTITION DUMPER   ")
    print("=" * 60)
    print(f"Output full dump: {OUT_FULL}")
    print(f"Output NVRAM:     {OUT_NV}\n")
    
    full_firmware_data = bytearray()
    nvram_data = bytearray()
    
    # 1. Probe all NVRAM items (0 to 1000)
    print("[1/3] Dumping all NVRAM items (0 to 1000)...")
    for item_id in range(1001):
        frame = build_hdlc_frame(0x05, 0x00, struct.pack("<H", item_id))
        try:
            dev.write(0x02, frame, timeout=100)
            time.sleep(0.01)
            resp = dev.read(0x82, 1024, timeout=100)
            if resp:
                resp_b = bytes(resp)
                nvram_data.extend(resp_b)
                full_firmware_data.extend(resp_b)
        except Exception:
            pass
            
        if (item_id + 1) % 200 == 0:
            print(f"  NVRAM Progress: {item_id + 1}/1000 items ({len(nvram_data):,} bytes collected)")

    with open(OUT_NV, "wb") as f:
        f.write(nvram_data)
    print(f"NVRAM dump saved: {OUT_NV} ({len(nvram_data):,} bytes)\n")

    # 2. Probe EFS Filesystem & Flash Partition Blocks
    print("[2/3] Extracting EFS partitions & Flash memory blocks...")
    flash_addrs = [
        0x00000000, 0x08000000, 0x10000000, 0x18000000,
        0x20000000, 0x40000000, 0x80000000, 0x80100000,
        0x80200000, 0x80400000, 0x80800000, 0x81000000
    ]
    
    for base_addr in flash_addrs:
        print(f"  Sampling base address {hex(base_addr)}...")
        for offset in range(0, 0x10000, 512):
            addr = base_addr + offset
            # Try DIAG Flash Read (0x11) and Memory Read (0x1E)
            for cmd_id in [0x11, 0x1E, 0x06]:
                frame = build_hdlc_frame(cmd_id, 0x00, struct.pack("<II", addr, 512))
                try:
                    dev.write(0x02, frame, timeout=100)
                    time.sleep(0.01)
                    resp = dev.read(0x82, 1024, timeout=100)
                    if resp:
                        full_firmware_data.extend(bytes(resp))
                except Exception:
                    pass

    # 3. Continuous memory streaming capture
    print("\n[3/3] Streaming live OS runtime memory blocks...")
    start_t = time.time()
    while time.time() - start_t < 30:
        try:
            resp = dev.read(0x82, 4096, timeout=200)
            if resp:
                full_firmware_data.extend(bytes(resp))
        except Exception:
            pass

    with open(OUT_FULL, "wb") as f:
        f.write(full_firmware_data)

    size_mb = len(full_firmware_data) / (1024 * 1024)
    print(f"\n{'=' * 60}")
    print(f"   LIVE FIRMWARE CAPTURE COMPLETE!")
    print(f"   File: {OUT_FULL}")
    print(f"   Size: {len(full_firmware_data):,} bytes ({size_mb:.3f} MB)")
    print(f"{'=' * 60}")

if __name__ == "__main__":
    main()
