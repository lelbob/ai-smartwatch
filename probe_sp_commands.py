import serial
import time

SP_COMMANDS = [
    "AT+SPAT=?",
    "AT+SPAT?",
    "AT+SPAT=1",
    "AT+SPAT=0",
    "AT+SPVER",
    "AT+SPVER?",
    "AT+SPENTERBOOT",
    "AT+SPDOWNLOAD",
    "AT+SPBOOT",
    "AT+SPDBG",
    "AT+SPDEVINFO",
    "AT+SPDEVINFO?",
    "AT+SPENHA=?",
    "AT+SPENHA?",
]

def main():
    print("=== Probing Spreadtrum AT Commands with Safe Hex Output ===")
    try:
        ser = serial.Serial('COM7', baudrate=115200, timeout=0.5, write_timeout=1)
        ser.dtr = True
        ser.rts = True
        
        for cmd_str in SP_COMMANDS:
            cmd = (cmd_str + "\r\n").encode()
            print(f"\nSending: {cmd_str}")
            ser.reset_input_buffer()
            ser.write(cmd)
            time.sleep(0.4)
            resp = ser.read(512)
            if resp:
                print(f"  Raw ({len(resp)} bytes): {resp[:100]!r}")
            else:
                print("  No response.")
                
        ser.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
