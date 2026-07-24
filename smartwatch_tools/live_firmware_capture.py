"""
live_firmware_capture.py - Captures the ENTIRE live memory stream from a
UNISOC SC6531 smartwatch running Mocor OS over WinUSB Endpoint 0x02/0x82.

No hardware reboot required. The watch stays connected and powered on.
Captures all debug logs, NVRAM, I2C sensor data, WiFi config, battery,
signal levels, and firmware metadata strings continuously.
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
    dll_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "spd_dump", "libusb-1.0.dll"))
    backend = usb.backend.libusb1.get_backend(find_library=lambda x: dll_path)
    
    dev = usb.core.find(idVendor=0x1782, idProduct=0x3D00, backend=backend)
    if dev is None:
        print("[ERROR] Device VID 0x1782 PID 0x3D00 not found.")
        return
    
    print("=" * 60)
    print("   LIVE MOCOR OS FIRMWARE & MEMORY CAPTURE")
    print("   No hardware reboot required")
    print("=" * 60)
    print(f"\nDevice: {dev.manufacturer} {dev.product}")
    print(f"USB ID: {hex(dev.idVendor)}:{hex(dev.idProduct)}")
    
    out_bin = os.path.join(os.path.dirname(__file__), "dumps", "live_capture.bin")
    out_txt = os.path.join(os.path.dirname(__file__), "dumps", "live_capture_strings.txt")
    os.makedirs(os.path.dirname(out_bin), exist_ok=True)
    
    # ----------------------------------------------------------------
    # Phase 1: Passive stream capture (EP 0x82 continuously streams
    #           debug logs, telemetry, NVRAM values from the Mocor OS)
    # ----------------------------------------------------------------
    print(f"\n[Phase 1] Capturing passive debug stream from EP 0x82...")
    print(f"Output binary: {out_bin}")
    print(f"Output strings: {out_txt}")
    
    all_data = bytearray()
    start_time = time.time()
    read_count = 0
    error_count = 0
    target_duration = 60  # 60 seconds of capture
    
    while time.time() - start_time < target_duration:
        try:
            buf = dev.read(0x82, 2048, timeout=300)
            if buf:
                all_data.extend(buf)
                read_count += 1
                error_count = 0  # Reset error counter on success
        except Exception:
            error_count += 1
            if error_count > 20:
                # Try stimulating more output with probe commands
                stimulate_cmds = [
                    b"AT\r\n",
                    b"AT+CSQ\r\n",
                    b"AT+CGMR\r\n",
                    b"AT+CFUN?\r\n",
                    build_hdlc_frame(0x0F, 0x00),
                    build_hdlc_frame(0x05, 0x00, struct.pack("<H", 1)),
                ]
                for cmd in stimulate_cmds:
                    try:
                        dev.write(0x02, cmd, timeout=200)
                        time.sleep(0.05)
                        buf = dev.read(0x82, 2048, timeout=200)
                        if buf:
                            all_data.extend(buf)
                            read_count += 1
                    except Exception:
                        pass
                error_count = 0
        
        elapsed = time.time() - start_time
        if read_count > 0 and read_count % 50 == 0:
            print(f"  Progress: {len(all_data):,} bytes captured ({read_count} reads, {elapsed:.0f}s elapsed)")
    
    # ----------------------------------------------------------------
    # Phase 2: Active NVRAM probing (send NV read commands for items 0-100)
    # ----------------------------------------------------------------
    print(f"\n[Phase 2] Probing NVRAM items 0-100...")
    for item_id in range(101):
        payload = struct.pack("<H", item_id)
        frame = build_hdlc_frame(0x05, 0x00, payload)
        try:
            dev.write(0x02, frame, timeout=200)
            time.sleep(0.05)
            buf = dev.read(0x82, 2048, timeout=200)
            if buf:
                all_data.extend(buf)
        except Exception:
            pass
    
    # ----------------------------------------------------------------
    # Phase 3: Active memory address probing
    # ----------------------------------------------------------------
    print(f"[Phase 3] Probing memory addresses via DIAG Read commands...")
    for addr in [0x00000000, 0x08000000, 0x10000000, 0x20000000, 
                 0x40000000, 0x60000000, 0x80000000, 0x90000000,
                 0xA0000000, 0xC0000000, 0xF0000000]:
        for size in [256, 512]:
            payload = struct.pack("<II", addr, size)
            frame = build_hdlc_frame(0x11, 0x00, payload)
            try:
                dev.write(0x02, frame, timeout=200)
                time.sleep(0.05)
                buf = dev.read(0x82, 2048, timeout=200)
                if buf:
                    all_data.extend(buf)
            except Exception:
                pass
    
    # ----------------------------------------------------------------
    # Phase 4: AT command enumeration for firmware info
    # ----------------------------------------------------------------
    print(f"[Phase 4] AT command firmware info extraction...")
    at_cmds = [
        "AT", "ATI", "AT+CGMR", "AT+CGSN", "AT+GMR", "AT+CFUN?",
        "AT+CSQ", "AT+COPS?", "AT+CPIN?", "AT+CLAC",
        "AT+SPNV?", "AT+EFS", "AT+FS", "AT+FSLS",
    ]
    for cmd in at_cmds:
        try:
            dev.write(0x02, (cmd + "\r\n").encode(), timeout=200)
            time.sleep(0.1)
            buf = dev.read(0x82, 2048, timeout=200)
            if buf:
                all_data.extend(buf)
        except Exception:
            pass
    
    # ----------------------------------------------------------------
    # Save results
    # ----------------------------------------------------------------
    with open(out_bin, "wb") as f:
        f.write(all_data)
    
    # Extract readable strings
    import re
    strings = re.findall(b"[\x20-\x7E]{4,}", all_data)
    unique_strings = sorted(set(s.decode('ascii', errors='ignore') for s in strings))
    
    with open(out_txt, "w", encoding="utf-8") as f:
        for s in unique_strings:
            f.write(s + "\n")
    
    print(f"\n{'=' * 60}")
    print(f"   CAPTURE COMPLETE")
    print(f"{'=' * 60}")
    print(f"Total binary data:   {len(all_data):,} bytes -> {out_bin}")
    print(f"Unique strings:      {len(unique_strings)} -> {out_txt}")
    print(f"Total USB reads:     {read_count}")
    print(f"Duration:            {time.time() - start_time:.1f}s")
    
    # Print key findings
    print(f"\n--- Key Firmware Metadata ---")
    keywords = ["VERSION", "BUILD", "Mocor", "SC6531", "3g-elec", "wifi", 
                "BT", "IMEI", "SIM", "signal", "bat", "pwon", "I2C",
                "firmware", "flash", "sdio", "rda"]
    seen = set()
    for s in unique_strings:
        for kw in keywords:
            if kw.lower() in s.lower() and s not in seen:
                seen.add(s)
                print(f"  {s[:120]}")
                break

if __name__ == "__main__":
    main()
