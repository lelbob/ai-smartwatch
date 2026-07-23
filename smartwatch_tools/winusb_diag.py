import usb.core
import usb.backend.libusb1
import os
import time

def main():
    dll_path = os.path.abspath("spd_dump\\libusb-1.0.dll")
    backend = usb.backend.libusb1.get_backend(find_library=lambda x: dll_path)
    
    dev = usb.core.find(idVendor=0x1782, idProduct=0x3D00, backend=backend)
    if dev is None:
        print("Device not found.")
        return
        
    try:
        dev.set_configuration(3)
    except Exception:
        pass
        
    print("=== WinUSB Direct Endpoint Communication (EP 0x02 / 0x82) ===")
    
    test_cmds = [
        ("AT", b"AT\r\n"),
        ("AT+CGMR", b"AT+CGMR\r\n"),
        ("AT+CGSN", b"AT+CGSN\r\n"),
        ("AT+SPAT?", b"AT+SPAT?\r\n"),
    ]
    
    for label, cmd in test_cmds:
        print(f"\nSending {label}...")
        try:
            dev.write(0x02, cmd, timeout=1000)
            time.sleep(0.3)
            resp = dev.read(0x82, 512, timeout=1000)
            txt = bytes(resp).decode('utf-8', errors='replace').strip()
            print(f"  Received ({len(resp)} bytes):")
            print(f"  {txt[:250]}")
        except Exception as e:
            print(f"  Error: {e}")

if __name__ == "__main__":
    main()
