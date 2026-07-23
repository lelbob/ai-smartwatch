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
    # Length of payload + header (2 bytes: cmd_id, sub_cmd)
    raw = bytes([cmd_id, sub_cmd]) + payload
    crc = sprd_crc16(raw)
    crc_bytes = struct.pack("<H", crc)
    packet = raw + crc_bytes
    
    # HDLC Byte stuffing (escape 0x7E -> 0x7D 0x5E, 0x7D -> 0x7D 0x5D)
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
    print("=== Testing HDLC Framed Spreadtrum DIAG Commands ===")
    
    test_packets = [
        ("GET_VERSION (0x0F)", build_hdlc_frame(0x0F, 0x00)),
        ("PING (0x00)", build_hdlc_frame(0x00, 0x00)),
        ("READ_NV_ITEM (0x05)", build_hdlc_frame(0x05, 0x00, struct.pack("<H", 1))), # Read NV item 1
        ("MODE_SWITCH_DOWNLOAD (0x0A)", build_hdlc_frame(0x0A, 0x01)), # Switch to download mode
        ("READ_FLASH (0x11)", build_hdlc_frame(0x11, 0x00, struct.pack("<II", 0x00000000, 0x100))), # Read 256 bytes from 0x0
    ]
    
    try:
        ser = serial.Serial('COM7', baudrate=115200, timeout=1, write_timeout=1)
        ser.dtr = True
        ser.rts = True
        
        for name, pkt in test_packets:
            print(f"\nSending {name} -> Raw frame: {pkt.hex()}")
            ser.reset_input_buffer()
            ser.write(pkt)
            time.sleep(0.5)
            resp = ser.read(512)
            if resp:
                print(f"  Response ({len(resp)} bytes): {resp[:64].hex()}")
                # Print any ascii string inside if present
                ascii_parts = ''.join([chr(b) if 32 <= b <= 126 else '.' for b in resp[:100]])
                print(f"  Ascii view: {ascii_parts}")
            else:
                print("  No response.")
                
        ser.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
