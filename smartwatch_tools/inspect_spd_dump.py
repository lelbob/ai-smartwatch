import re

def main():
    with open(r"spd_dump\spd_dump.exe", "rb") as f:
        data = f.read()
        
    strings = re.findall(b"[\x20-\x7E]{4,}", data)
    print(f"Total ASCII strings found: {len(strings)}")
    
    print("\n--- Key Flags & Arguments ---")
    for s in strings:
        st = s.decode('ascii', errors='ignore')
        if any(keyword in st for keyword in ["usage", "fdl", "read_flash", "baud", "port", "COM", "--"]):
            print(f"  {st}")

if __name__ == "__main__":
    main()
