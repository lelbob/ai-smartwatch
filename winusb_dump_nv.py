import usb.core
import usb.backend.libusb1
import os
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
    dll_path = os.path.abspath("spd_dump\\libusb-1.0.dll")
    backend = usb.backend.libusb1.get_backend(find_library=lambda x: dll_path)
    
    dev = usb.core.find(idVendor=0x1782, idProduct=0x3D00, backend=backend)
    if dev is None:
        print("Device not found.")
        return
        
    try:
        dev.set_configuration(3)
    except Exception:
        pass
        
    print("=== Direct WinUSB Diagnostic Data Capture ===")
    
    # Capture 50 chunks of live diagnostic buffers from Endpoint 0x82
    all_data = bytearray()
    out_file = "live_diag_stream.bin"
    
    print(f"Streaming live memory buffers to {out_file}...")
    start_time = time.time()
    
    for i in range(20):
        try:
            buf = dev.read(0x82, 512, timeout=1000)
            if buf:
                all_data.extend(buf)
        except Exception:
            pass
            
    with open(out_file, "wb") as f:
        f.write(all_data)
        
    print(f"\n[SUCCESS] Captured {len(all_data)} bytes of live diagnostic data to {out_file}!")
    
    # Inspect strings
    text_data = all_data.decode('utf-8', errors='replace')
    unique_lines = set([line.strip() for line in text_data.split('\n') if len(line.strip()) > 5])
    
    print("\n--- Unique Log Strings Discovered ---")
    for line in sorted(list(unique_lines))[:15]:
        print(f"  - {line}")

if __name__ == "__main__":
    main()
