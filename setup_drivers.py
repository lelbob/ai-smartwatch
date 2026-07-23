import os
import sys
import urllib.request
import zipfile
import subprocess
import ctypes

DRIVER_URL = "https://github.com/gsmusbdrivers/usbdrivers/raw/master/SPD_Driver_R4.20.4201.zip"
ZIP_NAME = "SPD_Driver_R4.20.4201.zip"
EXTRACT_DIR = "drivers"

def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        return False

def download_file(url, filename):
    print(f"Downloading {url}...")
    try:
        # User-Agent to prevent getting blocked
        req = urllib.request.Request(
            url, 
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        )
        with urllib.request.urlopen(req) as response, open(filename, 'wb') as out_file:
            data = response.read()
            out_file.write(data)
        print("Download completed successfully.")
        return True
    except Exception as e:
        print(f"Error downloading file: {e}")
        return False

def extract_zip(filename, extract_to):
    print(f"Extracting {filename} to {extract_to}...")
    try:
        with zipfile.ZipFile(filename, 'r') as zip_ref:
            zip_ref.extractall(extract_to)
        print("Extraction completed successfully.")
        return True
    except Exception as e:
        print(f"Error extracting zip: {e}")
        return False

def run_installer():
    # Identify system architecture
    is_64bit = sys.maxsize > 2**32
    
    # Locate DPInst inside the extracted directories
    dpinst_path = None
    for root, dirs, files in os.walk(EXTRACT_DIR):
        for file in files:
            if is_64bit and file.lower() == "dpinst64.exe":
                dpinst_path = os.path.join(root, file)
                break
            elif not is_64bit and file.lower() == "dpinst32.exe":
                dpinst_path = os.path.join(root, file)
                break
        if dpinst_path:
            break

    if not dpinst_path:
        print("Error: Could not locate DPInst installer in the extracted files.")
        return False

    abs_dpinst_path = os.path.abspath(dpinst_path)
    print(f"Located installer: {abs_dpinst_path}")

    # Run the installer with elevation (UAC prompt)
    print("\nLaunching driver installer...")
    print("A User Account Control (UAC) dialog will pop up requesting Administrator permission.")
    print("Please click 'Yes' or provide credentials to install the driver.")
    
    try:
        # shell32.ShellExecuteW to run as admin (runas verb)
        ret = ctypes.windll.shell32.ShellExecuteW(
            None, 
            "runas", 
            abs_dpinst_path, 
            "/sw", # Silent/wizard mode for DPInst
            None, 
            1 # SW_SHOWNORMAL
        )
        if ret > 32:
            print("Driver installer launched successfully. Follow the prompts in the installer window.")
            return True
        else:
            print(f"Failed to launch installer with admin rights. ShellExecute error code: {ret}")
            return False
    except Exception as e:
        print(f"Error launching installer: {e}")
        return False

def main():
    # Step 1: Download
    if not os.path.exists(ZIP_NAME):
        if not download_file(DRIVER_URL, ZIP_NAME):
            return
    else:
        print(f"ZIP file {ZIP_NAME} already exists, skipping download.")

    # Step 2: Extract
    if not os.path.exists(EXTRACT_DIR):
        if not extract_zip(ZIP_NAME, EXTRACT_DIR):
            return
    else:
        print(f"Directory {EXTRACT_DIR} already exists, skipping extraction.")

    # Step 3: Run installer
    run_installer()

if __name__ == "__main__":
    main()
