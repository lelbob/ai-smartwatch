import usb.core
import usb.util

def main():
    print("=== Scanning USB Devices via pyusb ===")
    dev = usb.core.find(idVendor=0x1782, idProduct=0x3D00)
    if dev is None:
        print("Device VID 1782 PID 3D00 not found by pyusb.")
        # Print all found devices
        all_devs = list(usb.core.find(find_all=True))
        print(f"Total USB devices found: {len(all_devs)}")
        for d in all_devs:
            print(f"  - VID: 0x{d.idVendor:04x}, PID: 0x{d.idProduct:04x}")
    else:
        print(f"Found Device: VID 0x{dev.idVendor:04x} PID 0x{dev.idProduct:04x}")
        for cfg in dev:
            print(f"  Config {cfg.bConfigurationValue}:")
            for intf in cfg:
                print(f"    Interface {intf.bInterfaceNumber}, Alt {intf.bAlternateSetting}:")
                for ep in intf:
                    print(f"      Endpoint 0x{ep.bEndpointAddress:02x} (Type: {ep.bmAttributes})")

if __name__ == "__main__":
    main()
