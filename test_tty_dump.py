import subprocess
import os

SPD_DIR = os.path.abspath("spd_dump")
SPD_DUMP = os.path.join(SPD_DIR, "spd_dump.exe")
FDL1 = os.path.join(SPD_DIR, "t117_fdl1.bin")
OUT_BIN = os.path.abspath("firmware_tty.bin")

def main():
    print("=== Testing spd_dump over --tty COM7 ===")
    cmd = [
        SPD_DUMP,
        "--tty", "COM7",
        "--wait", "5",
        "fdl", FDL1, "0x40004000",
        "read_flash", "0x80000000", "0", "16M", OUT_BIN
    ]
    
    print(f"Executing: {' '.join(cmd)}")
    res = subprocess.run(cmd, capture_output=True, text=True, cwd=SPD_DIR)
    print("--- STDOUT ---")
    print(res.stdout)
    print("--- STDERR ---")
    print(res.stderr)

if __name__ == "__main__":
    main()
