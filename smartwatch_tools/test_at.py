import sys
import time

try:
    import serial
    from serial.tools import list_ports
except ImportError:
    print("Error: 'pyserial' library is not installed. Please run 'pip install pyserial' first.")
    sys.exit(1)

def test_port(port_name):
    print(f"Testing port {port_name}...")
    try:
        # Open port with a short timeout to prevent long hangs
        ser = serial.Serial(port_name, baudrate=115200, timeout=1, write_timeout=1)
        
        # Send AT test
        print(f"  Sending: AT\\r\\n")
        ser.write(b"AT\r\n")
        time.sleep(0.2)
        response = ser.read_all()
        if response:
            print(f"  Received: {response!r}")
            if b"OK" in response.upper():
                print(f"  --> Found active AT response on {port_name}!")
                
                # Query device information
                for cmd in [b"ATI", b"AT+CGMR", b"AT+CGMM", b"AT+CGSN"]:
                    print(f"  Sending: {cmd.decode()}\\r\\n")
                    ser.write(cmd + b"\r\n")
                    time.sleep(0.2)
                    resp = ser.read_all()
                    print(f"  Received:\n{resp.decode('utf-8', errors='ignore').strip()}")
                ser.close()
                return True
        ser.close()
    except Exception as e:
        print(f"  Failed to communicate: {e}")
    return False

def main():
    # Explicitly look for SPRD/Spreadtrum or COM8 first
    ports = list(list_ports.comports())
    
    target_ports = []
    other_ports = []
    
    for p in ports:
        desc = p.description.upper()
        # Skip Bluetooth ports as they cause hangs on Windows
        if "BLUETOOTH" in desc or "BTHENUM" in p.hwid.upper():
            print(f"Skipping Bluetooth port: {p.device} ({p.description})")
            continue
            
        if "SPRD" in desc or "SPREADTRUM" in desc or p.device.upper() == "COM8":
            target_ports.append(p)
        else:
            other_ports.append(p)
            
    # Put target ports first
    scanned_ports = target_ports + other_ports
    
    if not scanned_ports:
        print("No suitable COM ports found to scan (Bluetooth ports skipped).")
        return
        
    print(f"Scanned COM ports in order:")
    for p in scanned_ports:
        print(f"- {p.device}: {p.description}")
        
    found_any = False
    for p in scanned_ports:
        if test_port(p.device):
            found_any = True
            break # Stop after finding the first responding AT port
            
    if not found_any:
        print("\nCould not establish AT communication on any port.")

if __name__ == "__main__":
    main()
