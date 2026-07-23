import subprocess
import os

SPD_DIR = os.path.abspath("spd_dump")
SPD_DUMP = os.path.join(SPD_DIR, "spd_dump.exe")
FDL1 = os.path.join(SPD_DIR, "t117_fdl1.bin")
OUT_BIN = os.path.abspath("firmware_tty.bin")

def test_cmd(args):
    cmd = [SPD_DUMP] + args
    print(f"\nExecuting: {' '.join(cmd)}")
    res = subprocess.run(cmd, capture_output=True, text=True, cwd=SPD_DIR)
    print(f"Stdout: {res.stdout.strip()}")
    print(f"Stderr: {res.stderr.strip()}")

def main():
    test_cmd(["--tty", "\\\\.\\COM7", "--wait", "2", "fdl", FDL1, "0x40004000"])
    test_cmd(["--tty", "\\\\.\\COM8", "--wait", "2", "fdl", FDL1, "0x40004000"])

if __name__ == "__main__":
    main()
