import subprocess
import os
import sys

SPD_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "spd_dump"))
SPD_DUMP = os.path.join(SPD_DIR, "spd_dump.exe")
FDL_NOR = os.path.join(SPD_DIR, "nor_fdl1.bin")
FDL_T117 = os.path.join(SPD_DIR, "t117_fdl1.bin")
OUT_BIN = os.path.abspath("firmware_dump.bin")

def main():
    print("=" * 60)
    print("   spd_dump is now WAITING FOR YOUR WATCH (120 SECONDS)...   ")
    print("=" * 60)
    print()
    print("INSTRUCTIONS:")
    print("  1. Unplug the USB cable from the PC.")
    print("  2. Turn OFF the smartwatch.")
    print("  3. Hold the SECOND / CHARGING button on the watch.")
    print("  4. Plug the USB cable back into the PC while holding the button.")
    print()
    
    cmd = [
        SPD_DUMP,
        "--wait", "120",
        "fdl", FDL_T117, "0x40004000",
        "read_flash", "0x80000000", "0", "16M", OUT_BIN
    ]
    
    print(f"Executing: {' '.join(cmd)}")
    res = subprocess.run(cmd, capture_output=True, text=True, cwd=SPD_DIR)
    print("\n--- STDOUT ---")
    print(res.stdout)
    print("\n--- STDERR ---")
    print(res.stderr)
    
    if os.path.exists(OUT_BIN) and os.path.getsize(OUT_BIN) > 0:
        print(f"\n[SUCCESS!] Firmware dumped: {OUT_BIN} ({os.path.getsize(OUT_BIN)} bytes)")
    else:
        print("\nTrying secondary loader nor_fdl1.bin...")
        cmd2 = [
            SPD_DUMP,
            "--wait", "60",
            "fdl", FDL_NOR, "0x40004000",
            "read_flash", "0x80000000", "0", "16M", OUT_BIN
        ]
        res2 = subprocess.run(cmd2, capture_output=True, text=True, cwd=SPD_DIR)
        print(res2.stdout)
        print(res2.stderr)

if __name__ == "__main__":
    main()
