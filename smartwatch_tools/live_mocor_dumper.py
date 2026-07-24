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
    dll_path = os.path.abspath("smartwatch_tools/spd_dump/libusb-1.0.dll")
    backend = usb.backend.libusb1.get_backend(find_library=lambda x: dll_path)
    
    dev = usb.core.find(idVendor=0x1782, idProduct=0x3D00, backend=backend)
    if dev is None:
        print("Device not found.")
        return
        
    print("=" * 60)
    print("   LIVE MOCOR OS MEMORY & FIRMWARE DUMPER (NO HARDWARE REBOOT)   ")
    print("=" * 60)
    print("Device connected over WinUSB / libusbK (PID 0x3D00)\n")
    
    # Test commands to probe live memory access
    test_frames = [
        # AT Tunnel (0x38)
        ("AT Tunnel (AT+CGMR)", build_hdlc_frame(0x38, 0x00, b"AT+CGMR\r\n")),
        ("AT Tunnel (AT+EFS)", build_hdlc_frame(0x38, 0x00, b"AT+EFS\r\n")),
        # NVRAM Read (0x05)
        ("NVRAM Read Item 1", build_hdlc_frame(0x05, 0x00, struct.pack("<H", 1))),
        ("NVRAM Read Item 2", build_hdlc_frame(0x05, 0x00, struct.pack("<H", 2))),
        # DIAG Flash Read (0x11)
        ("DIAG Flash Read 0x80000000", build_hdlc_frame(0x11, 0x00, struct.pack("<II", 0x80000000, 256))),
        ("DIAG Flash Read 0x00000000", build_hdlc_frame(0x11, 0x00, struct.pack("<II", 0x00000000, 256))),
        # DIAG Sys Info (0x0F)
        ("DIAG Sys Info (0x0F)", build_hdlc_frame(0x0F, 0x00)),
        # Memory Dump (0x1E)
        ("DIAG Memory Dump (0x1E)", build_hdlc_frame(0x1E, 0x00, struct.pack("<II", 0x80000000, 256))),
    ]
    
    for ep_out, ep_in in [(0x02, 0x82), (0x03, 0x83)]:
        print(f"\n--- Testing Endpoints OUT {hex(ep_out)} / IN {hex(ep_in)} ---")
        for label, frame in test_frames:
            try:
                # Flush input buffer first
                try:
                    dev.read(ep_in, 1024, timeout=100)
                except Exception:
                    pass
                    
                dev.write(ep_out, frame, timeout=500)
                time.sleep(0.1)
                resp = dev.read(ep_in, 2048, timeout=500)
                if resp:
                    resp_bytes = bytes(resp)
                    print(f"  {label} -> Response ({len(resp_bytes)} bytes): {resp_bytes[:40].hex()}")
                    # Inspect ASCII strings
                    text = "".join([chr(b) if 32 <= b <= 126 else "." for b in resp_bytes[:100]])
                    print(f"  ASCII: {text}")
                else:
                    print(f"  {label} -> Empty response")
            except Exception as e:
                print(f"  {label} -> Error: {e}")

if __name__ == "__main__":
    main()
