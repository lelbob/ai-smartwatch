import serial.tools.list_ports

def main():
    ports = serial.tools.list_ports.comports()
    print(f"Active COM Ports ({len(ports)} found):")
    for p in ports:
        print(f"  - {p.device}: {p.description} [{p.hwid}]")

if __name__ == "__main__":
    main()
