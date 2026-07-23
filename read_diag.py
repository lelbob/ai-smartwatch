import serial
import time
import sys

def main():
    port = "COM7"
    print(f"Opening {port} to read debug logs for 15 seconds...")
    try:
        ser = serial.Serial(port, baudrate=115200, timeout=1)
        start_time = time.time()
        
        # Flush buffers
        ser.reset_input_buffer()
        
        while time.time() - start_time < 15:
            if ser.in_waiting > 0:
                data = ser.read(ser.in_waiting)
                sys.stdout.buffer.write(data)
                sys.stdout.flush()
            time.sleep(0.05)
            
        ser.close()
        print("\n\nFinished reading logs.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
