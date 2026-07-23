import subprocess

def main():
    print("Checking processes using serial ports or handle locks...")
    ps_script = """
    Get-Process | Where-Object { $_.ProcessName -like "*python*" -or $_.ProcessName -like "*spd*" } | Select-Object Id, ProcessName, Path | Format-Table -AutoSize
    """
    res = subprocess.run(["powershell", "-Command", ps_script], capture_output=True, text=True)
    print(res.stdout)

if __name__ == "__main__":
    main()
