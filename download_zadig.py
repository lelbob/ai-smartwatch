import urllib.request
import os

ZADIG_URL = "https://github.com/pbatard/libwdi/releases/download/v1.5.1/zadig-2.9.exe"
TOOLS_DIR = os.path.abspath("tools")
ZADIG_PATH = os.path.join(TOOLS_DIR, "zadig.exe")

def main():
    os.makedirs(TOOLS_DIR, exist_ok=True)
    print(f"Downloading Zadig 2.9 from {ZADIG_URL}...")
    
    req = urllib.request.Request(
        ZADIG_URL,
        headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    )
    with urllib.request.urlopen(req) as r, open(ZADIG_PATH, 'wb') as f:
        f.write(r.read())
        
    print(f"\n[SUCCESS] Downloaded Zadig to: {ZADIG_PATH}")
    print(f"File size: {os.path.getsize(ZADIG_PATH)} bytes")

if __name__ == "__main__":
    main()
