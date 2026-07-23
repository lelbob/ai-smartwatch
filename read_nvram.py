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
    print("=== Dump NVRAM items over COM7 (SPRD DIAG) ===")
    
    try:
        ser = serial.Serial('COM7', baudrate=115200, timeout=0.5, write_timeout=1)
        ser.dtr = True
        ser.rts = True
        
        found_nv = []
        
        # Test NV items from 0 to 50
        for item_id in range(1, 30):
            # Command 0x05 (READ_NV_ITEM)
            # Payload: item_id (2 bytes LE)
            payload = struct.pack("<H", item_id)
            frame = build_hdlc_frame(0x05, 0x00, payload)
            
            ser.reset_input_buffer()
            ser.write(frame)
            time.sleep(0.15)
            resp = ser.read(512)
            
            if resp:
                # Filter out passive debug log strings
                clean_resp = [b for b in resp.split(b"\n") if not b.startswith(b"is_gprs_attached") and not b.startswith(b"read_imsi")]
                if clean_resp:
                    print(f"NV Item #{item_id}: {resp[:60].hex()}")
                    found_nv.append((item_id, resp))
                    
        ser.close()
        print(f"\nFinished probing NV items. Found {len(found_nv)} responses.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
