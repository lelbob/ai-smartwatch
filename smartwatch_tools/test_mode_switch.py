import serial
import time
import struct
import subprocess

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

def check_pnp_devices():
    res = subprocess.run(
        ["powershell", "-Command", "Get-PnpDevice -PresentOnly | Where-Object DeviceID -like '*1782*' | Select-Object FriendlyName, DeviceID | ConvertTo-Json"],
        capture_output=True, text=True
    )
    print("Present 1782 Devices:")
    print(res.stdout)

def main():
    print("=== Sending Mode Switch to Download Mode ===")
    check_pnp_devices()
    
    try:
        ser = serial.Serial('COM7', baudrate=115200, timeout=1, write_timeout=1)
        ser.dtr = True
        ser.rts = True
        
        # Test Mode Switch variants
        # 1. 0x0A 0x01 (Download Mode)
        # 2. 0x0A 0x00 (Bootrom Mode)
        # 3. 0x0A 0x04 (Autodownload)
        
        for mode in [0x01, 0x00, 0x04]:
            pkt = build_hdlc_frame(0x0A, mode)
            print(f"\nSending Mode Switch (sub_cmd={mode}) -> Frame: {pkt.hex()}")
            ser.write(pkt)
            time.sleep(1)
            resp = ser.read(512)
            if resp:
                print(f"Response: {resp[:100].hex()}")
            else:
                print("No serial response (device might be resetting!).")
                
        ser.close()
    except Exception as e:
        print(f"Serial exception: {e}")
        
    print("\nWaiting 2 seconds then checking USB devices again...")
    time.sleep(2)
    check_pnp_devices()

if __name__ == "__main__":
    main()
