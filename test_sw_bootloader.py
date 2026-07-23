import serial
import time

REBOOT_CMDS = [
    b"AT+RESET\r\n",
    b"AT+REBOOT\r\n",
    b"AT+CFUN=1,1\r\n",
    b"AT+SPAT=1\r\n",
    b"AT+SPENHA=1\r\n",
    b"reboot\r\n",
    b"reset\r\n",
    # SPRD Mode switch binary frame: 0x7E 0x0A ... 0x7E (Command 0x0A is mode switch to download)
    bytes([0x7E, 0x0A, 0x00, 0x8D, 0x12, 0x7E]),
]

def try_reboot_cmds(port_name):
    print(f"=== Testing software reboot commands on {port_name} ===")
    try:
        ser = serial.Serial(port_name, baudrate=115200, timeout=1, write_timeout=1)
        ser.dtr = True
        ser.rts = True
        
        for cmd in REBOOT_CMDS:
            print(f"Sending {cmd[:25]}...")
            try:
                ser.write(cmd)
                time.sleep(0.3)
                resp = ser.read(256)
                if resp:
                    print(f"  Resp: {resp.decode('utf-8', errors='replace').strip()[:100]}")
            except Exception as e:
                print(f"  Error: {e}")
        ser.close()
    except Exception as e:
        print(f"Could not open {port_name}: {e}")

if __name__ == "__main__":
    try_reboot_cmds("COM7")
