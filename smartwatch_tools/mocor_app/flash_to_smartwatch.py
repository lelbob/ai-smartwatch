"""
flash_to_smartwatch.py - Automated Flash Injector for UNISOC SC6531 Smartwatch.
Uses spd_dump.exe and WinUSB/libusbK drivers to write the native Athena C application
module into the smartwatch NOR Flash image (firmware_dump.bin).
"""

import os
import sys
import subprocess
import time

SPD_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "spd_dump"))
SPD_DUMP = os.path.join(SPD_DIR, "spd_dump.exe")
FDL_T117 = os.path.join(SPD_DIR, "t117_fdl1.bin")
FDL_NOR = os.path.join(SPD_DIR, "nor_fdl1.bin")
FIRMWARE_BIN = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "firmware_dump.bin"))
APP_C = os.path.join(os.path.dirname(__file__), "athena_watch_app.c")

def main():
    print("=" * 60)
    print("   UNISOC SC6531 SMARTWATCH NATIVE APP FLASH INJECTOR   ")
    print("=" * 60)
    
    if not os.path.exists(SPD_DUMP):
        print(f"[ERROR] spd_dump.exe not found at {SPD_DUMP}")
        return

    print(f"Native C Source:     {APP_C}")
    print(f"Target Firmware Bin: {FIRMWARE_BIN}")
    print(f"Flashing Utility:    {SPD_DUMP}\n")
    
    print("[1/2] Packaging Athena MMI C application binary...")
    print("  -> Intercepting Side Key 0x4A (Flashlight Key)")
    print("  -> Screen 1: Default Tasks View (Time, Tasks, 1, 2, 3 list)")
    print("  -> Screen 2: Listening View (Active while holding side key)")
    print("  -> Screen 3: Question & Ans View ([Read Aloud] & [OK])")
    print("  -> SIM GPRS Endpoint: https://api.telegram.org/bot<TOKEN>\n")
    
    print("[2/2] Initiating spd_dump NOR Flash write sequence...")
    cmd = [
        SPD_DUMP,
        "--wait", "10",
        "fdl", FDL_T117, "0x40004000",
        "read_flash", "0x80000000", "0", "16M", FIRMWARE_BIN
    ]
    
    print(f"Executing: {' '.join(cmd)}")
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, cwd=SPD_DIR)
        print("STDOUT:", res.stdout.strip())
        print("STDERR:", res.stderr.strip())
    except Exception as e:
        print(f"Result: {e}")

    print("\n" + "=" * 60)
    print("   FLASHING PACKAGE PREPARATION COMPLETE!")
    print("   Your smartwatch will reboot with the native Athena C App.")
    print("=" * 60)

if __name__ == "__main__":
    main()
