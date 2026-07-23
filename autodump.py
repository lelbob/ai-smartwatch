import subprocess
import serial
import time
import struct
import os
import sys

SPD_DIR = os.path.abspath("spd_dump")
SPD_DUMP = os.path.join(SPD_DIR, "spd_dump.exe")
FDL1 = os.path.join(SPD_DIR, "t117_fdl1.bin")

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

def send_soft_reset():
    print("Opening COM7 (DIAG) to trigger soft-reset via AT tunnel...")
    try:
        ser = serial.Serial('COM7', baudrate=115200, timeout=1, write_timeout=1)
        ser.dtr = True
        ser.rts = True
        
        pkt1 = build_hdlc_frame(0x38, 0x00, b"AT+CFUN=1,1\r\n")
        pkt2 = build_hdlc_frame(0x38, 0x00, b"AT+RESET\r\n")
        pkt3 = build_hdlc_frame(0x0A, 0x01)
        
        print("Sending AT+CFUN=1,1 tunnel...")
        ser.write(pkt1)
        time.sleep(0.2)
        print("Sending AT+RESET tunnel...")
        ser.write(pkt2)
        time.sleep(0.2)
        print("Sending Mode Switch Download frame...")
        ser.write(pkt3)
        time.sleep(0.2)
        
        ser.close()
        print("Soft reset commands sent.")
    except Exception as e:
        print(f"Serial reset error: {e}")

def main():
    print("=" * 60)
    print("      UNISOC SC6531 Smartwatch Automated Firmware Dumper      ")
    print("=" * 60)
    
    out_bin = os.path.abspath("firmware_dump.bin")
    
    print(f"spd_dump tool path: {SPD_DUMP}")
    print(f"FDL loader path:    {FDL1}")
    
    # 1. Trigger soft reset on COM7
    send_soft_reset()
    
    print("\nLaunching spd_dump to catch BootROM reset...")
    cmd = [
        SPD_DUMP,
        "--wait", "5",
        "fdl", FDL1, "0x40004000",
        "read_flash", "0x80000000", "0", "16M", out_bin
    ]
    
    print(f"Executing: {' '.join(cmd)}")
    res = subprocess.run(cmd, capture_output=True, text=True, cwd=SPD_DIR)
    print(res.stdout)
    if res.stderr:
        print(f"Stderr: {res.stderr}")
        
    if os.path.exists(out_bin) and os.path.getsize(out_bin) > 0:
        print(f"\n[SUCCESS] Firmware dumped to {out_bin} ({os.path.getsize(out_bin)} bytes)!")
    else:
        print("\n[INFO] Run finished.")

if __name__ == "__main__":
    main()
