import winreg
import re
import subprocess
import time

def get_unisoc_devices():
    devices = []
    usb_path = r"SYSTEM\CurrentControlSet\Enum\USB"
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, usb_path) as usb_key:
            num_subkeys = winreg.QueryInfoKey(usb_key)[0]
            for i in range(num_subkeys):
                subkey_name = winreg.EnumKey(usb_key, i)
                if "VID_1782" in subkey_name.upper():
                    # This is a Spreadtrum / UNISOC device key
                    device_path = usb_path + "\\" + subkey_name
                    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, device_path) as dev_key:
                        num_instances = winreg.QueryInfoKey(dev_key)[0]
                        for j in range(num_instances):
                            instance_name = winreg.EnumKey(dev_key, j)
                            instance_path = device_path + "\\" + instance_name
                            try:
                                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, instance_path) as inst_key:
                                    try:
                                        friendly_name = winreg.QueryValueEx(inst_key, "FriendlyName")[0]
                                    except FileNotFoundError:
                                        friendly_name = "Generic/Unknown Unisoc Device"
                                    
                                    try:
                                        location_paths = winreg.QueryValueEx(inst_key, "LocationPaths")[0]
                                    except FileNotFoundError:
                                        location_paths = ""
                                    
                                    # Check for COM port assignment in Device Parameters
                                    com_port = None
                                    try:
                                        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, instance_path + "\\Device Parameters") as param_key:
                                            com_port = winreg.QueryValueEx(param_key, "PortName")[0]
                                    except FileNotFoundError:
                                        pass
                                    
                                    devices.append({
                                        "HardwareID": subkey_name,
                                        "InstanceID": instance_name,
                                        "FriendlyName": friendly_name,
                                        "COMPort": com_port
                                    })
                            except Exception:
                                pass
    except Exception as e:
        print(f"Error reading registry: {e}")
    return devices

def main():
    print("==================================================")
    print("         Spreadtrum / UNISOC Device Finder        ")
    print("==================================================")
    
    devices = get_unisoc_devices()
    if not devices:
        print("No Spreadtrum/UNISOC devices found in registry history.")
        print("Please ensure the watch is plugged in.")
        return
        
    print(f"Found {len(devices)} device entry(ies) in system registry:\n")
    for idx, dev in enumerate(devices, 1):
        print(f"Device #{idx}:")
        print(f"  Hardware ID:  {dev['HardwareID']}")
        print(f"  Instance ID:  {dev['InstanceID']}")
        print(f"  Friendly Name: {dev['FriendlyName']}")
        if dev['COMPort']:
            print(f"  COM Port:     {dev['COMPort']} (Driver installed!)")
        else:
            print("  COM Port:     None (Driver is missing/not configured - 'null')")
        print("-" * 50)

    print("\n[TIP] If COM Port is 'None', Windows does not know how to talk to it.")
    print("To fix this, you can manually bind the standard Windows USB Serial driver:")
    print("1. Open Device Manager (Win + X -> Device Manager).")
    print("2. Locate the device under 'Other Devices' or 'Universal Serial Bus controllers' with a yellow exclamation mark.")
    print("3. Right-click it and select 'Update Driver'.")
    print("4. Choose 'Browse my computer for drivers' -> 'Let me pick from a list of available drivers'.")
    print("5. Select 'Ports (COM & LPT)' -> Manufacturer: 'Microsoft' -> Model: 'USB Serial Device'.")
    print("6. Click Next and click Yes/Install if prompted.")

if __name__ == "__main__":
    main()
