import subprocess
import json

def main():
    cmd = ["powershell", "-Command", "Get-PnpDevice | Where-Object { $_.InstanceId -like '*1782*' } | Select-Object FriendlyName, InstanceId, Status, Class | ConvertTo-Json"]
    res = subprocess.run(cmd, capture_output=True, text=True)
    print("All 1782 PnP Devices (Present & Historical):")
    print(res.stdout)

if __name__ == "__main__":
    main()
