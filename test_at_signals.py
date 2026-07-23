import serial
import time

def test_at_signals():
    print("Testing COM8 with DTR/RTS signals enabled...")
    try:
        ser = serial.Serial()
        ser.port = 'COM8'
        ser.baudrate = 115200
        ser.timeout = 1
        ser.write_timeout = 1
        ser.rtscts = False
        ser.dsrdtr = False
        
        ser.open()
        ser.dtr = True
        ser.rts = True
        time.sleep(0.1)
        
        print("COM8 opened with DTR=True, RTS=True.")
        
        for cmd in [b"AT\r\n", b"ATI\r\n", b"AT+CGMR\r\n"]:
            print(f"Sending {cmd.strip().decode()}...")
            try:
                ser.write(cmd)
                time.sleep(0.3)
                resp = ser.read(512)
                print(f"  Response ({len(resp)} bytes): {resp.decode('utf-8', errors='replace').strip()}")
            except Exception as e:
                print(f"  Write/Read Error: {e}")
                
        ser.close()
    except Exception as e:
        print(f"Open Error: {e}")

if __name__ == "__main__":
    test_at_signals()
