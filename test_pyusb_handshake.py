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
        
    print("Setting active configuration (Config 3)...")
    try:
        dev.set_configuration(3)
        print("Configuration 3 set!")
    except Exception as e:
        print(f"set_configuration info: {e}")
        
    # Endpoint 0x02 (OUT) and 0x82 (IN) on Interface 1
    # Endpoint 0x03 (OUT) and 0x83 (IN) on Interface 0
    
    print("\n--- Testing Handshake on Interface 1 (EP 0x02 / 0x82) ---")
    try:
        # BROM PING packet: 0x7E 0x00 0x00 0x00 0x00 0x7E
        ping_pkt = bytes([0x7E, 0x00, 0x00, 0x00, 0x00, 0x7E])
        dev.write(0x02, ping_pkt, timeout=1000)
        resp = dev.read(0x82, 512, timeout=1000)
        print(f"Interface 1 Response ({len(resp)} bytes): {bytes(resp).hex()}")
    except Exception as e:
        print(f"Interface 1 Error: {e}")
        
    print("\n--- Testing Handshake on Interface 0 (EP 0x03 / 0x83) ---")
    try:
        ping_pkt = bytes([0x7E, 0x00, 0x00, 0x00, 0x00, 0x7E])
        dev.write(0x03, ping_pkt, timeout=1000)
        resp = dev.read(0x83, 512, timeout=1000)
        print(f"Interface 0 Response ({len(resp)} bytes): {bytes(resp).hex()}")
    except Exception as e:
        print(f"Interface 0 Error: {e}")

if __name__ == "__main__":
    main()
