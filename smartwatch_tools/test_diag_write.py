import serial
import time

def test_diag():
    print("Opening COM7 (DIAG)...")
    try:
        ser = serial.Serial('COM7', baudrate=115200, timeout=1, write_timeout=1)
        ser.dtr = True
        ser.rts = True
        print("COM7 opened.")
        
        # Read initial stream
        init_data = ser.read(256)
        print(f"Initial stream: {init_data.decode('utf-8', errors='replace').strip()[:200]}")
        
        # Test sending commands to DIAG port
        test_cmds = [
            b"AT\r\n",
            b"help\r\n",
            bytes([0x7E, 0x00, 0x00, 0x9E, 0xFD, 0x7E]), # SPRD NOP
            bytes([0x7E, 0x0F, 0x00, 0xAB, 0xF3, 0x7E]), # SPRD Version query
        ]
        
        for cmd in test_cmds:
            print(f"\nSending to COM7: {cmd[:20]}")
            ser.write(cmd)
            time.sleep(0.5)
            resp = ser.read(512)
            if resp:
                print(f"Response ({len(resp)} bytes): {resp[:100]}")
                print(f"Text: {resp.decode('utf-8', errors='replace').strip()[:200]}")
            else:
                print("No response.")
                
        ser.close()
        print("COM7 closed.")
    except Exception as e:
        print(f"Error on COM7: {e}")

if __name__ == "__main__":
    test_diag()
