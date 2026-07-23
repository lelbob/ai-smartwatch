import serial
import time

def main():
    print("=== Listening to COM7 (DIAG) for 3 seconds ===")
    try:
        ser7 = serial.Serial('COM7', 115200, timeout=1)
        start = time.time()
        buf = b""
        while time.time() - start < 3:
            data = ser7.read(512)
            if data:
                buf += data
        ser7.close()
        print(f"COM7 Received {len(buf)} bytes:")
        try:
            print(buf.decode('utf-8', errors='replace')[:500])
        except Exception:
            print(buf[:100].hex())
    except Exception as e:
        print(f"COM7 Error: {e}")

    print("\n=== Testing COM8 (AT Port) ===")
    try:
        ser8 = serial.Serial('COM8', 115200, timeout=1)
        ser8.write(b"AT\r\n")
        time.sleep(0.5)
        resp = ser8.read(256)
        ser8.close()
        print(f"COM8 Response ({len(resp)} bytes): {resp}")
    except Exception as e:
        print(f"COM8 Error: {e}")

if __name__ == "__main__":
    main()
