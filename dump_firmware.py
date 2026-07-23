import subprocess
import os
import sys
import time

def main():
    print("==================================================")
    print("        Spreadtrum / UNISOC Firmware Dumper        ")
    print("==================================================")
    
    # Paths
    spd_dump_dir = "spd_dump"
    spd_dump_exe = os.path.join(spd_dump_dir, "spd_dump.exe")
    nor_fdl1 = os.path.join(spd_dump_dir, "nor_fdl1.bin")
    output_bin = "smartwatch_firmware_backup.bin"
    
    if not os.path.exists(spd_dump_exe):
        print(f"Error: {spd_dump_exe} not found. Please run download_spd_dump.py first.")
        return
        
    print("\n[INSTRUCTIONS] How to enter BootROM Mode:")
    print("1. Turn the watch completely OFF (hold power button until it shuts down).")
    print("2. Keep the USB cable UNPLUGGED from the PC.")
    print("3. Press and HOLD the SOS or Power button on the watch.")
    print("4. While holding the button, plug the USB cable into the PC.")
    print("5. The tool will automatically detect it and start the dump.")
    
    # We will use 16MB (16M) as a safe default size to dump everything.
    # We can trim it later if the flash is smaller.
    cmd = [
        spd_dump_exe,
        "fdl", nor_fdl1, "0x40004000",
        "read_flash", "0x80000003", "0", "16M", output_bin
    ]
    
    print("\nLaunching spd_dump.exe. It will wait for the device...")
    print("Command:", " ".join(cmd))
    print("\nWaiting for device... (Press Ctrl+C to cancel)")
    
    try:
        # Run spd_dump and stream output to console
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
        
        while True:
            output = process.stdout.readline()
            if output == '' and process.poll() is not None:
                break
            if output:
                print(output.strip())
                
        rc = process.poll()
        if rc == 0:
            print("\n==================================================")
            print(" SUCCESS: Firmware dumped successfully!")
            print(f" Saved to: {os.path.abspath(output_bin)}")
            print("==================================================")
        else:
            print(f"\nFailed to dump firmware. Exit code: {rc}")
            
    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")
        if 'process' in locals():
            process.terminate()

if __name__ == "__main__":
    main()
