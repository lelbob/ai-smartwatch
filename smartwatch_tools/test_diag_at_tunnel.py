import serial
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
    print("=== Testing AT Tunneling & Memory Read via DIAG (COM7) ===")
    
    # 0x38: AT Tunneling (Payload is AT command string)
    # 0x13: Memory Read (Addr 4 bytes, Len 4 bytes)
    # 0x15: EFS Read
    
    test_frames = [
        ("AT Tunnel: AT (0x38)", build_hdlc_frame(0x38, 0x00, b"AT\r\n")),
        ("AT Tunnel: AT+CGMR (0x38)", build_hdlc_frame(0x38, 0x00, b"AT+CGMR\r\n")),
        ("AT Tunnel: AT+CFUN=1,1 (0x38)", build_hdlc_frame(0x38, 0x00, b"AT+CFUN=1,1\r\n")),
        ("Mem Read @ 0x00000000 len 64 (0x13)", build_hdlc_frame(0x13, 0x00, struct.pack("<II", 0x00000000, 64))),
        ("Mem Read @ 0x40000000 len 64 (0x13)", build_hdlc_frame(0x13, 0x00, struct.pack("<II", 0x40000000, 64))),
        ("Mem Read @ 0x80000000 len 64 (0x13)", build_hdlc_frame(0x13, 0x00, struct.pack("<II", 0x80000000, 64))),
    ]
    
    try:
        ser = serial.Serial('COM7', baudrate=115200, timeout=1, write_timeout=1)
        ser.dtr = True
        ser.rts = True
        
        for name, pkt in test_frames:
            print(f"\nSending {name} -> Frame: {pkt.hex()}")
            ser.reset_input_buffer()
            ser.write(pkt)
            time.sleep(0.5)
            resp = ser.read(512)
            if resp:
                print(f"  Resp ({len(resp)} bytes): {resp[:80].hex()}")
                ascii_parts = ''.join([chr(b) if 32 <= b <= 126 else '.' for b in resp[:100]])
                print(f"  Ascii: {ascii_parts}")
            else:
                print("  No response.")
                
        ser.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
