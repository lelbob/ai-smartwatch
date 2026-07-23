import serial
import time
import sys

def try_config(port, baud, rtscts, dsrdtr):
    print(f"Trying {port} at {baud} baud, rtscts={rtscts}, dsrdtr={dsrdtr}...")
    try:
        ser = serial.Serial(port, baudrate=baud, timeout=1, write_timeout=1, rtscts=rtscts, dsrdtr=dsrdtr)
        
        # Clear buffers
        ser.reset_input_buffer()
        ser.reset_output_buffer()
        
        # Test 1: AT\r\n
        print("  Sending: AT\\r\\n")
        ser.write(b"AT\r\n")
        time.sleep(0.2)
        resp = ser.read_all()
        if resp:
            print(f"  --> Response: {resp!r}")
            ser.close()
            return True
            
        # Test 2: AT\r
        print("  Sending: AT\\r")
        ser.write(b"AT\r")
        time.sleep(0.2)
        resp = ser.read_all()
        if resp:
            print(f"  --> Response: {resp!r}")
            ser.close()
            return True
            
        ser.close()
    except Exception as e:
        print(f"  Failed with this config: {e}")
    return False

def main():
    port = "COM8"
    configs = [
        # (baud, rtscts, dsrdtr)
        (115200, False, False),
        (115200, True, False),
        (115200, False, True),
        (9600, False, False),
        (9600, True, False),
        (57600, False, False),
        (460800, False, False),
        (921600, False, False),
    ]
    
    for baud, rts, dtr in configs:
        if try_config(port, baud, rts, dtr):
            print("\nSuccessfully established communication!")
            return
            
    print("\nCould not get AT response from COM8.")

if __name__ == "__main__":
    main()
