import subprocess
import os
import sys

SPD_DIR = os.path.abspath("spd_dump")
SPD_DUMP = os.path.join(SPD_DIR, "spd_dump.exe")
FDL_T117 = os.path.join(SPD_DIR, "t117_fdl1.bin")
FDL_NOR  = os.path.join(SPD_DIR, "nor_fdl1.bin")
OUT_BIN  = os.path.abspath("firmware_dump.bin")

def run_dump(fdl_path, name):
    print(f"\n--- Trying spd_dump with loader: {name} ---")
    cmd = [
        SPD_DUMP,
        "--wait", "5",
        "fdl", fdl_path, "0x40004000",
        "read_flash", "0x80000000", "0", "16M", OUT_BIN
    ]
    print(f"Executing: {' '.join(cmd)}")
    res = subprocess.run(cmd, capture_output=True, text=True, cwd=SPD_DIR)
    print("STDOUT:")
    print(res.stdout)
    print("STDERR:")
    print(res.stderr)
    
    if os.path.exists(OUT_BIN) and os.path.getsize(OUT_BIN) > 0:
        print(f"\nSUCCESS! Dump file created: {OUT_BIN} ({os.path.getsize(OUT_BIN)} bytes)")
        return True
    return False

def main():
    print("=== Automated Firmware Dump Attempt ===")
    if not run_dump(FDL_T117, "t117_fdl1.bin"):
        run_dump(FDL_NOR, "nor_fdl1.bin")

if __name__ == "__main__":
    main()
