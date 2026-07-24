"""
coolsand_flash_reader.py - Reads NOR flash memory from a LIVE running
Coolsand SC6531 smartwatch using multiple protocol variants.

Tries:
1. Coolsand Host Monitor protocol (0xAD framing)
2. Spreadtrum HDLC DIAG protocol (0x7E framing) 
3. Raw memory read commands
4. Continuous bulk stream capture from both endpoint pairs

No hardware reboot required.
"""

import usb.core
import usb.backend.libusb1
import os
import time
import struct
import sys

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

def coolsand_read_mem(addr, length):
    """Coolsand Host Monitor memory read command."""
    # Format: 0xAD + cmd(1) + addr(4 BE) + len(4 BE) + checksum
    cmd = 0x01  # Read memory
    payload = struct.pack(">BII", cmd, addr, length)
    checksum = sum(payload) & 0xFF
    return bytes([0xAD]) + payload + bytes([checksum, 0xAD])

def coolsand_read_mem_v2(addr, length):
    """Alternative Coolsand framing with 0xAD header."""
    header = struct.pack(">BBII", 0xAD, 0x52, addr, length)  # 0x52 = 'R' for Read
    return header

def rda_read_flash(addr, length):
    """RDA/Coolsand flash read - another variant."""
    # Some Coolsand tools use: magic(2) + cmd(1) + addr(4) + len(4)
    return struct.pack("<HB", 0xBBBB, 0x01) + struct.pack("<II", addr, length)

def main():
    dll_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "spd_dump", "libusb-1.0.dll"))
    backend = usb.backend.libusb1.get_backend(find_library=lambda x: dll_path)
    
    dev = usb.core.find(idVendor=0x1782, idProduct=0x3D00, backend=backend)
    if dev is None:
        print("[ERROR] Device not found.")
        return
    
    print("=" * 60)
    print("   COOLSAND SC6531 LIVE FLASH READER")
    print("   Multi-protocol memory extraction")
    print("=" * 60)
    
    out_dir = os.path.join(os.path.dirname(__file__), "dumps")
    os.makedirs(out_dir, exist_ok=True)
    
    all_data = bytearray()
    flash_data = bytearray()
    
    base_addr = 0x80000000
    chunk_size = 256
    
    # ----------------------------------------------------------------
    # Test 1: Coolsand Host Monitor on both EP pairs
    # ----------------------------------------------------------------
    print("\n[Test 1] Coolsand Host Monitor protocol...")
    
    for ep_out, ep_in, iface in [(0x03, 0x83, 0), (0x02, 0x82, 1)]:
        print(f"\n  Interface {iface} (EP {hex(ep_out)}/{hex(ep_in)}):")
        
        for addr in [0x80000000, 0x00000000, 0x08000000]:
            for builder, label in [
                (lambda a, s: coolsand_read_mem(a, s), "Host Monitor v1"),
                (lambda a, s: coolsand_read_mem_v2(a, s), "Host Monitor v2"),
                (lambda a, s: rda_read_flash(a, s), "RDA Flash Read"),
                (lambda a, s: build_hdlc_frame(0x11, 0x00, struct.pack("<II", a, s)), "HDLC Flash Read"),
                (lambda a, s: build_hdlc_frame(0x13, 0x00, struct.pack("<II", a, s)), "HDLC Mem Read"),
                (lambda a, s: build_hdlc_frame(0x1E, 0x00, struct.pack("<II", a, s)), "HDLC Mem Dump"),
            ]:
                frame = builder(addr, chunk_size)
                try:
                    # Flush
                    try:
                        dev.read(ep_in, 2048, timeout=50)
                    except:
                        pass
                    
                    dev.write(ep_out, frame, timeout=300)
                    time.sleep(0.05)
                    resp = dev.read(ep_in, 4096, timeout=300)
                    resp_bytes = bytes(resp)
                    
                    # Check if response contains non-debug-log binary data
                    is_debug = b"is_gprs" in resp_bytes or b"wifi_" in resp_bytes or b"pwon_count" in resp_bytes
                    
                    if not is_debug and len(resp_bytes) > 0:
                        print(f"    *** {label} @ {hex(addr)}: BINARY DATA! ({len(resp_bytes)} bytes)")
                        print(f"        Hex: {resp_bytes[:48].hex()}")
                        flash_data.extend(resp_bytes)
                    elif len(resp_bytes) > 0:
                        print(f"    {label} @ {hex(addr)}: debug log ({len(resp_bytes)} bytes)")
                    
                    all_data.extend(resp_bytes)
                except Exception as e:
                    err_str = str(e)
                    if "timed out" not in err_str:
                        print(f"    {label} @ {hex(addr)}: {err_str}")
    
    # ----------------------------------------------------------------
    # Test 2: Raw bulk read - just read continuously from EP 0x83
    # ----------------------------------------------------------------
    print("\n[Test 2] Raw bulk read from EP 0x83 (Interface 0)...")
    ep83_data = bytearray()
    for i in range(50):
        try:
            buf = dev.read(0x83, 4096, timeout=200)
            if buf:
                ep83_data.extend(buf)
                is_debug = b"is_gprs" in bytes(buf) or b"wifi_" in bytes(buf)
                if not is_debug:
                    print(f"  Read {i}: BINARY DATA ({len(buf)} bytes): {bytes(buf)[:32].hex()}")
                    flash_data.extend(buf)
        except:
            pass
    print(f"  EP 0x83 total: {len(ep83_data)} bytes")
    
    # ----------------------------------------------------------------
    # Test 3: Stimulate EP 0x83 by writing probe commands to EP 0x03
    # ----------------------------------------------------------------
    print("\n[Test 3] Stimulating EP 0x03 with various command bytes...")
    
    raw_probes = [
        bytes([0x7E]),                              # HDLC flag
        bytes([0xAD]),                              # Coolsand marker
        bytes([0x7E, 0x7E]),                        # Double flag
        bytes([0x55, 0xAA]),                        # Sync pattern
        bytes([0xFE, 0xFF]),                        # Alt sync
        b"\x7e\x00\x00\x00\x00\x7e",               # BROM ping
        bytes([0x7E, 0x04, 0x00, 0x00, 0x00, 0x7E]),  # Connect
        bytes(range(256)),                          # Full byte range
    ]
    
    for i, probe in enumerate(raw_probes):
        try:
            dev.write(0x03, probe, timeout=200)
            time.sleep(0.1)
            resp = dev.read(0x83, 4096, timeout=200)
            if resp:
                resp_bytes = bytes(resp)
                is_debug = b"is_gprs" in resp_bytes or b"wifi_" in resp_bytes
                if not is_debug:
                    print(f"  Probe {i}: RESPONSE ({len(resp_bytes)} bytes): {resp_bytes[:32].hex()}")
                    flash_data.extend(resp_bytes)
                else:
                    print(f"  Probe {i}: debug log ({len(resp_bytes)} bytes)")
                all_data.extend(resp_bytes)
        except:
            pass
    
    # ----------------------------------------------------------------
    # Test 4: Extended EP 0x82 bulk capture (5 minutes continuous)
    # ----------------------------------------------------------------
    print("\n[Test 4] Extended 5-minute continuous capture from EP 0x82...")
    start = time.time()
    read_count = 0
    stim_interval = 0
    
    while time.time() - start < 300:  # 5 minutes
        try:
            buf = dev.read(0x82, 4096, timeout=200)
            if buf:
                all_data.extend(buf)
                read_count += 1
        except:
            stim_interval += 1
            if stim_interval % 10 == 0:
                # Stimulate with various commands
                stim_cmds = [
                    b"AT\r\n",
                    build_hdlc_frame(0x0F, 0x00),
                    build_hdlc_frame(0x05, 0x00, struct.pack("<H", stim_interval % 100)),
                    build_hdlc_frame(0x11, 0x00, struct.pack("<II", 0x80000000 + (stim_interval * 256), 256)),
                ]
                for cmd in stim_cmds:
                    try:
                        dev.write(0x02, cmd, timeout=100)
                        time.sleep(0.02)
                        buf = dev.read(0x82, 4096, timeout=100)
                        if buf:
                            all_data.extend(buf)
                            read_count += 1
                    except:
                        pass
        
        elapsed = time.time() - start
        if read_count > 0 and read_count % 200 == 0:
            print(f"  {elapsed:.0f}s: {len(all_data):,} bytes total ({read_count} reads)")
    
    # ----------------------------------------------------------------
    # Save everything
    # ----------------------------------------------------------------
    all_bin = os.path.join(out_dir, "full_live_capture.bin")
    flash_bin = os.path.join(out_dir, "flash_data.bin")
    strings_txt = os.path.join(out_dir, "full_capture_strings.txt")
    
    with open(all_bin, "wb") as f:
        f.write(all_data)
    
    if flash_data:
        with open(flash_bin, "wb") as f:
            f.write(flash_data)
    
    import re
    strings = re.findall(b"[\x20-\x7E]{4,}", all_data)
    unique_strings = sorted(set(s.decode('ascii', errors='ignore') for s in strings))
    
    with open(strings_txt, "w", encoding="utf-8") as f:
        for s in unique_strings:
            f.write(s + "\n")
    
    print(f"\n{'=' * 60}")
    print(f"   CAPTURE COMPLETE")
    print(f"{'=' * 60}")
    print(f"Total data captured:   {len(all_data):,} bytes -> {all_bin}")
    print(f"Flash binary data:     {len(flash_data):,} bytes -> {flash_bin}")
    print(f"Unique strings:        {len(unique_strings)} -> {strings_txt}")
    print(f"Total reads:           {read_count}")
    print(f"Duration:              {time.time() - start:.0f}s")

if __name__ == "__main__":
    main()
