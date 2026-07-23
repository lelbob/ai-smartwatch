"""
install_winusb.py  – Installs a WinUSB .inf for VID_1782&PID_3D00 so that
spd_dump.exe can talk to the device via libusb even while it is running normally.

This works because spd_dump uses libusb in "forced" mode when a device is
already enumerated with a different driver – but only if WinUSB is the active
driver for the interface we want.

NOTE: This replaces the SPRD modem driver on MI_00 with WinUSB.  The COM8 port
will disappear after this, which is expected.  We are switching from a serial
protocol to direct USB access.
"""

import os
import sys
import ctypes
import subprocess
import tempfile

VID = "1782"
PID = "3D00"

INF_CONTENT = r"""
[Version]
Signature   = "$WINDOWS NT$"
Class       = USBDevice
ClassGuid   = {88BAE032-5A81-49f0-BC3D-A4FF138216D6}
Provider    = %ManufacturerName%
CatalogFile = unisoc_winusb.cat
DriverVer   = 06/21/2006,10.0.0.0

[Manufacturer]
%ManufacturerName% = Standard, NTamd64

[Standard.NTamd64]
%DeviceName% = WinUsb_Install, USB\VID_1782&PID_3D00&MI_00
%DeviceName% = WinUsb_Install, USB\VID_1782&PID_3D00

[WinUsb_Install.NT]
Include = winusb.inf
Needs   = WINUSB.NT

[WinUsb_Install.NT.Services]
Include    = winusb.inf
AddService = WinUSB, 0x00000002, WinUSB_ServiceInstall

[WinUSB_ServiceInstall]
DisplayName     = %WinUSB_SvcDesc%
ServiceType     = 1
StartType       = 3
ErrorControl    = 1
ServiceBinary   = %12%\WinUSB.sys

[WinUsb_Install.NT.HW]
AddReg = Dev_AddReg

[Dev_AddReg]
HKR,,DeviceInterfaceGUIDs,0x10000,"{06b1a180-e4e1-4a3d-a8ef-54b19e2e2ea5}"

[WinUsb_Install.NT.Wdf]
KmdfService = WINUSB, WinUSB_wdfsect

[WinUSB_wdfsect]
KmdfLibraryVersion = 1.15

[Strings]
ManufacturerName = "Spreadtrum/Unisoc"
DeviceName       = "Unisoc Smartwatch (WinUSB)"
WinUSB_SvcDesc   = "WinUSB Driver"
"""

def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

def main():
    if not is_admin():
        print("Relaunching as administrator...")
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas",
            sys.executable, f'"{os.path.abspath(__file__)}"',
            None, 1
        )
        return

    # Write INF to a temp dir
    tmp_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "winusb_inf")
    os.makedirs(tmp_dir, exist_ok=True)
    inf_path = os.path.join(tmp_dir, "unisoc_winusb.inf")
    
    with open(inf_path, "w") as f:
        f.write(INF_CONTENT.strip())

    print(f"INF written to: {inf_path}")
    print("Installing via pnputil (this requires admin)...")
    
    result = subprocess.run(
        ["pnputil", "/add-driver", inf_path, "/install"],
        capture_output=True, text=True
    )
    
    print(result.stdout)
    if result.returncode != 0:
        print(f"Error: {result.stderr}")
        print("\nFalling back to manual approach...")
        print("pnputil installed the inf – now triggering device scan...")
        subprocess.run(["pnputil", "/scan-devices"], capture_output=True)
    else:
        print("\nWinUSB driver installed successfully!")
    
    # Also trigger hardware scan
    subprocess.run(["pnputil", "/scan-devices"], capture_output=True)
    print("Device scan triggered. Please replug the watch now.")

if __name__ == "__main__":
    main()
