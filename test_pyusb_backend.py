import usb.core
import usb.backend.libusb1
import os

def main():
    dll_path = os.path.abspath("spd_dump\\libusb-1.0.dll")
    print(f"Loading backend from: {dll_path}")
    backend = usb.backend.libusb1.get_backend(find_library=lambda x: dll_path)
    
    print("Finding device VID 0x1782 PID 0x3D00...")
    dev = usb.core.find(idVendor=0x1782, idProduct=0x3D00, backend=backend)
    
    if dev is None:
        print("Device not found directly. Searching all USB devices...")
        all_devs = list(usb.core.find(find_all=True, backend=backend))
        print(f"Total USB devices found: {len(all_devs)}")
        for d in all_devs:
            print(f"  - VID: 0x{d.idVendor:04x}, PID: 0x{d.idProduct:04x}")
    else:
        print(f"\n[SUCCESS] Found Device: VID 0x{dev.idVendor:04x} PID 0x{dev.idProduct:04x}")
        for cfg in dev:
            print(f"  Config {cfg.bConfigurationValue}:")
            for intf in cfg:
                print(f"    Interface {intf.bInterfaceNumber}, Alt {intf.bAlternateSetting}:")
                for ep in intf:
                    print(f"      Endpoint 0x{ep.bEndpointAddress:02x} (Attributes: {ep.bmAttributes})")

if __name__ == "__main__":
    main()
