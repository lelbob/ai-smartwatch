import os
import sys
import json
import urllib.request
import zipfile

API_URL = "https://api.github.com/repos/ilyakurdyukov/spreadtrum_flash/releases/latest"
TARGET_DIR = "spd_dump"

def download_url(url, filepath):
    print(f"Downloading {url} to {filepath}...")
    try:
        req = urllib.request.Request(
            url, 
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        )
        with urllib.request.urlopen(req) as response, open(filepath, 'wb') as out_file:
            out_file.write(response.read())
        print("  Download successful.")
        return True
    except Exception as e:
        print(f"  Error downloading {url}: {e}")
        return False

def main():
    if not os.path.exists(TARGET_DIR):
        os.makedirs(TARGET_DIR)
        
    print("Fetching latest release information from GitHub...")
    try:
        req = urllib.request.Request(
            API_URL,
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        )
        with urllib.request.urlopen(req) as response:
            release_info = json.loads(response.read().decode())
    except Exception as e:
        print(f"Error fetching release info: {e}")
        return

    tag_name = release_info.get("tag_name", "unknown")
    print(f"Latest release found: {tag_name}")
    
    assets = release_info.get("assets", [])
    if not assets:
        print("No assets found in the latest release.")
        return

    zip_path = None
    for asset in assets:
        name = asset.get("name", "")
        download_url_str = asset.get("browser_download_url", "")
        
        # We want to download the 64-bit zip and any bin/loader files
        if "spd_dump64" in name.lower() and name.endswith(".zip"):
            zip_path = os.path.join(TARGET_DIR, name)
            download_url(download_url_str, zip_path)
        elif name.endswith(".bin"):
            bin_path = os.path.join(TARGET_DIR, name)
            download_url(download_url_str, bin_path)

    if zip_path and os.path.exists(zip_path):
        print(f"Extracting {zip_path}...")
        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(TARGET_DIR)
            print("Extraction successful.")
            # Remove the zip file after extraction
            os.remove(zip_path)
        except Exception as e:
            print(f"Error extracting zip: {e}")
            
    print("\nInitialization complete. Files in spd_dump directory:")
    for f in os.listdir(TARGET_DIR):
        print(f"- {f}")

if __name__ == "__main__":
    main()
