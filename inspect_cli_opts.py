import re

def main():
    with open(r"spd_dump\spd_dump.exe", "rb") as f:
        data = f.read()
        
    # Find all format strings or command line string options
    opts = re.findall(b"-[a-zA-Z0-9_-]+", data)
    print("Found options:")
    seen = set()
    for o in opts:
        st = o.decode('ascii', errors='ignore')
        if st not in seen:
            seen.add(st)
            print(f"  {st}")

if __name__ == "__main__":
    main()
