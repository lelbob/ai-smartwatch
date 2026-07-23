"""
autobind_winusb.py - Automatically binds Windows built-in WinUSB driver to VID_1782&PID_3D00
using newdev.dll API with elevated Administrator privileges.
"""

import ctypes
import sys
import os
import subprocess

def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        return False

def bind_winusb():
    if not is_admin():
        print("Requesting administrator privileges...")
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas",
            sys.executable, f'"{os.path.abspath(__file__)}"',
            None, 1
        )
        return

    print("=== Automating WinUSB Driver Binding ===")
    
    # 1. Create custom INF pointing to built-in WinUSB
    inf_dir = os.path.abspath("winusb_driver")
    os.makedirs(inf_dir, exist_ok=True)
    inf_file = os.path.join(inf_dir, "unisoc_winusb.inf")
    
    inf_content = r"""
[Version]
Signature="$WINDOWS NT$"
Class=USBDevice
ClassGUID={88BAE032-5A81-49f0-BC3D-A4FF138216D6}
Provider=%Vendor%
CatalogFile=unisoc.cat
DriverVer=01/01/2026,1.0.0.0

[Manufacturer]
%Vendor%=UnisocWinUsb,NTamd64

[UnisocWinUsb.NTamd64]
%DeviceName%=USB_Install, USB\VID_1782&PID_3D00
%DeviceName%=USB_Install, USB\VID_1782&PID_3D00&MI_00
%DeviceName%=USB_Install, USB\VID_1782&PID_3D00&MI_01

[USB_Install]
Include=winusb.inf
Needs=WINUSB.NT

[USB_Install.Services]
Include=winusb.inf
AddService=WinUSB,0x00000002,WinUSB_ServiceInstall

[WinUSB_ServiceInstall]
DisplayName=%WinUSB_SvcDesc%
ServiceType=1
StartType=3
ErrorControl=1
ServiceBinary=%12%\WinUSB.sys

[USB_Install.HW]
AddReg=Dev_AddReg

[Dev_AddReg]
HKR,,DeviceInterfaceGUIDs,0x10000,"{06b1a180-e4e1-4a3d-a8ef-54b19e2e2ea5}"

[Strings]
Vendor="Spreadtrum / Unisoc"
DeviceName="Unisoc Smartwatch (WinUSB Direct)"
WinUSB_SvcDesc="WinUSB Driver Service"
"""
    
    with open(inf_file, "w") as f:
        f.write(inf_content.strip())
        
    print(f"Generated INF: {inf_file}")
    
    # Run devcon / pnputil / UpdateDriverForPlugAndPlayDevicesW
    hwid = "USB\\VID_1782&PID_3D00"
    print(f"Binding {hwid} to WinUSB via newdev.dll...")
    
    newdev = ctypes.windll.newdev
    bRebootRequired = ctypes.c_bool(False)
    
    # INSTALLFLAG_FORCE = 0x00000001
    ret = newdev.UpdateDriverForPlugAndPlayDevicesW(
        None,
        hwid,
        inf_file,
        1, # FORCE
        ctypes.byref(bRebootRequired)
    )
    
    if ret:
        print("[SUCCESS] WinUSB driver successfully bound to VID_1782&PID_3D00!")
    else:
        err = ctypes.GetLastError()
        print(f"[INFO] UpdateDriver returned false (WinError code: {err})")
        print("Executing pnputil scan-devices fallback...")
        subprocess.run(["pnputil", "/scan-devices"], capture_output=True)

if __name__ == "__main__":
    bind_winusb()
