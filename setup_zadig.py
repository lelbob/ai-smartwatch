import urllib.request
import os

ZADIG_URL = "https://github.com/pbatard/zadig/releases/download/v2.9/zadig-2.9.exe"
ZADIG_PATH = "tools\\zadig.exe"

def main():
    if not os.path.exists("tools"):
        os.makedirs("tools")
    
    if os.path.exists(ZADIG_PATH):
        print(f"Zadig already exists at {ZADIG_PATH}")
    else:
        print(f"Downloading Zadig from {ZADIG_URL}...")
        try:
            req = urllib.request.Request(
                ZADIG_URL,
                headers={'User-Agent': 'Mozilla/5.0'}
            )
            with urllib.request.urlopen(req) as r, open(ZADIG_PATH, 'wb') as f:
                f.write(r.read())
            print("Download complete.")
        except Exception as e:
            print(f"Error: {e}")
            return
    
    print(f"\nZadig is ready at: {os.path.abspath(ZADIG_PATH)}")
    print("\n=== INSTRUCTIONS ===")
    print("1. Make sure the watch is turned ON and plugged in normally.")
    print("2. Run: tools\\zadig.exe (as Administrator)")
    print("3. Go to: Options -> List All Devices")
    print("4. In the dropdown, find 'SPRD AT' or 'USB Serial Device' (the one with USB ID 1782 3D00)")
    print("5. On the right side of the arrow, select 'WinUSB' from the drop-down")
    print("6. Click 'Replace Driver'")
    print("")
    print("NOTE: After replacing the driver, the COM8 serial port will disappear")
    print("and spd_dump will be able to use the device directly via USB.")
    print("")
    print("7. Then try spd_dump again - ALSO hold the button while plugging in to try BootROM mode.")

if __name__ == "__main__":
    main()
