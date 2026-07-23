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
    log_lines = []
    print("=== Direct NV item probe (1 to 10) ===")
    try:
        ser = serial.Serial('COM7', baudrate=115200, timeout=0.3, write_timeout=1)
        ser.dtr = True
        ser.rts = True
        
        for item_id in range(1, 10):
            payload = struct.pack("<H", item_id)
            frame = build_hdlc_frame(0x05, 0x00, payload)
            ser.reset_input_buffer()
            ser.write(frame)
            time.sleep(0.1)
            resp = ser.read(256)
            msg = f"Item #{item_id}: {resp.hex() if resp else 'No resp'}"
            print(msg)
            log_lines.append(msg)
            
        ser.close()
    except Exception as e:
        print(f"Error: {e}")
        
    with open("nv_log.txt", "w") as f:
        f.write("\n".join(log_lines))

if __name__ == "__main__":
    main()
