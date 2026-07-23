import serial
import time

def test_at():
    print("Opening COM8...")
    try:
        ser = serial.Serial('COM8', baudrate=115200, timeout=1, write_timeout=1)
        print("COM8 opened successfully.")
        
        commands = [b"AT\r\n", b"ATI\r\n", b"AT+CGMR\r\n", b"AT+CSQ\r\n", b"AT+CBC\r\n"]
        for cmd in commands:
            print(f"Sending: {cmd.strip().decode()}")
            ser.write(cmd)
            time.sleep(0.3)
            out = ser.read(512)
            if out:
                print(f"  Received ({len(out)} bytes): {out.decode('utf-8', errors='replace').strip()}")
            else:
                print("  No response.")
        ser.close()
        print("COM8 closed.")
    except Exception as e:
        print(f"Error on COM8: {e}")

if __name__ == "__main__":
    test_at()
