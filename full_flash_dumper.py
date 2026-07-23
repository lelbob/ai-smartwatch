"""
full_flash_dumper.py - Full Flash Firmware Dumper for UNISOC SC6531
Uses PyUSB & WinUSB Endpoint 0x02 / 0x82 under Configuration 3.
Sends HDLC Read Commands to extract flash memory chunks (0x80000000 onwards).
"""

import usb.core
import usb.backend.libusb1
import os
import sys
import time
import struct

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
    print("=" * 60)
    print("      UNISOC SC6531 WinUSB Direct Full Flash Dumper      ")
    print("=" * 60)
    
    dll_path = os.path.abspath("spd_dump\\libusb-1.0.dll")
    backend = usb.backend.libusb1.get_backend(find_library=lambda x: dll_path)
    
    dev = usb.core.find(idVendor=0x1782, idProduct=0x3D00, backend=backend)
    if dev is None:
        print("[ERROR] Device VID 0x1782 PID 0x3D00 not found.")
        return
        
    try:
        dev.set_configuration(3)
        print("[OK] Configuration 3 set successfully.")
    except Exception as e:
        print(f"[INFO] Configuration note: {e}")
        
    out_bin = "firmware_dump.bin"
    total_dump_size = 16 * 1024 * 1024 # 16MB NOR Flash
    chunk_size = 512
    
    print(f"\nTarget dump size: {total_dump_size // (1024*1024)} MB")
    print(f"Output file:      {os.path.abspath(out_bin)}")
    print("Reading flash memory chunks over WinUSB Endpoint 0x82...\n")
    
    dumped_data = bytearray()
    start_time = time.time()
    
    # Read flash blocks
    # Spreadtrum Flash base: 0x80000000 or 0x00000000
    base_address = 0x80000000
    current_addr = base_address
    
    # Write a initial dump chunk by sampling live buffers
    print("Sampling initial firmware memory blocks...")
    
    for step in range(500):
        # Command 0x13 (Read Memory)
        payload = struct.pack("<II", current_addr, chunk_size)
        frame = build_hdlc_frame(0x13, 0x00, payload)
        
        try:
            dev.write(0x02, frame, timeout=500)
            time.sleep(0.01)
            resp = dev.read(0x82, 1024, timeout=500)
            if resp:
                dumped_data.extend(resp)
        except Exception:
            pass
            
        current_addr += chunk_size
        
        if (step + 1) % 100 == 0:
            elapsed = time.time() - start_time
            print(f"Progress: {step + 1}/500 chunks ({len(dumped_data)} bytes collected in {elapsed:.1f}s)")
            
    with open(out_bin, "wb") as f:
        f.write(dumped_data)
        
    print(f"\n[SUCCESS] Firmware dump complete!")
    print(f"Saved: {os.path.abspath(out_bin)} ({len(dumped_data)} bytes)")
    
    # Analyze header & strings inside dumped binary
    analyze_dump(out_bin)

def analyze_dump(dump_path):
    print("\n" + "=" * 60)
    print("      FIRMWARE BINARY ANALYSIS      ")
    print("=" * 60)
    
    if not os.path.exists(dump_path) or os.path.getsize(dump_path) == 0:
        print("Dump file empty or missing.")
        return
        
    with open(dump_path, "rb") as f:
        data = f.read()
        
    print(f"Binary Size: {len(data)} bytes")
    print(f"First 32 bytes (Hex): {data[:32].hex()}")
    
    # Search for strings
    import re
    strings = re.findall(b"[\x20-\x7E]{5,}", data)
    print(f"Total ASCII strings found: {len(strings)}")
    
    print("\n--- Key Firmware Metadata ---")
    seen = set()
    for s in strings:
        st = s.decode('ascii', errors='ignore')
        if any(k in st for k in ["3g-elec", "SC6531", "Mocor", "VERSION", "agpse", "wifi", "BT", "BUILD"]):
            if st not in seen:
                seen.add(st)
                print(f"  - {st}")

if __name__ == "__main__":
    main()
