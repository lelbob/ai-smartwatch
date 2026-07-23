import serial
import time
import struct
import os

FDL_PATH = os.path.abspath("spd_dump\\nor_fdl1.bin")

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

def make_frame(cmd_id: int, sub_cmd: int = 0, payload: bytes = b"") -> bytes:
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
    print("=== Testing Direct BROM Protocol Handshake over COM7 ===")
    
    try:
        ser = serial.Serial('COM7', baudrate=115200, timeout=0.2, write_timeout=1)
        ser.dtr = True
        ser.rts = True
        
        # 1. Send BROM CONNECT frame repeatedly (50 times)
        # BROM PING packet: 0x7E 0x00 0x00 0x00 0x00 0x7E
        ping_pkt = bytes([0x7E, 0x00, 0x00, 0x00, 0x00, 0x7E])
        
        print("Sending BROM CONNECT sequence...")
        got_ack = False
        for i in range(30):
            ser.write(ping_pkt)
            time.sleep(0.05)
            resp = ser.read(128)
            if resp and b"\x7e" in resp:
                print(f"Received response on attempt {i+1}: {resp.hex()}")
                got_ack = True
                break
                
        if not got_ack:
            print("No BROM ACK received over standard COM7 mode.")
            
        ser.close()
    except Exception as e:
        print(f"Serial error: {e}")

if __name__ == "__main__":
    main()
