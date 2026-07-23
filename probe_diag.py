"""
probe_diag.py - Probes COM7 (SPRD DIAG) for any command interface:
  - Tries Spreadtrum binary protocol commands
  - Tries AT commands at different speeds  
  - Tries plain text commands the firmware might accept
  - Dumps all responses to a log file for analysis
"""

import serial
import time
import os
import sys

DIAG_PORT = "COM7"
AT_PORT   = "COM8"
LOG_FILE  = "diag_probe_log.txt"

# Spreadtrum DIAG binary framing: 0x7E + cmd_id + payload + crc + 0x7E
# Command 0x0F = get chip version
# Command 0x00 = ping (NOP)
SPRD_PING  = bytes([0x7E, 0x00, 0x00, 0x9E, 0xFD, 0x7E])
SPRD_VER   = bytes([0x7E, 0x0F, 0x00, 0xAB, 0xF3, 0x7E])

# Some Spreadtrum firmwares accept plain text cmds on DIAG
TEXT_CMDS = [
    b"AT\r\n",
    b"AT+CGMR\r\n",
    b"at\r\n",
    b"ver\r\n",
    b"version\r\n",
    b"help\r\n",
    b"dump\r\n",
]

results = []

def log(msg):
    print(msg)
    results.append(msg)

def try_port(port, baud, label, commands, binary=False):
    log(f"\n--- Testing {label} on {port} @ {baud} baud ---")
    try:
        ser = serial.Serial(port, baudrate=baud, timeout=1, write_timeout=2)
        ser.reset_input_buffer()
        time.sleep(0.2)
        
        # First: see if anything is streaming passively
        passive = ser.read(256)
        if passive:
            log(f"  Passive data received ({len(passive)} bytes):")
            try:
                log(f"  Text: {passive.decode('utf-8', errors='replace')[:200]}")
            except:
                log(f"  Hex:  {passive.hex()}")
        
        for cmd in commands:
            try:
                ser.reset_input_buffer()
                if binary:
                    label_cmd = cmd.hex()
                else:
                    label_cmd = cmd.decode('utf-8', errors='replace').strip()
                log(f"  Sending: {label_cmd}")
                ser.write(cmd)
                time.sleep(0.5)
                response = ser.read(512)
                if response:
                    log(f"  Response ({len(response)} bytes):")
                    try:
                        txt = response.decode('utf-8', errors='replace')
                        log(f"  Text: {txt[:300]}")
                    except:
                        pass
                    log(f"  Hex:  {response[:64].hex()}")
                else:
                    log(f"  No response.")
            except Exception as e:
                log(f"  Error sending command: {e}")
        
        ser.close()
    except Exception as e:
        log(f"  Cannot open port: {e}")

def main():
    log("=" * 60)
    log("  Spreadtrum Diagnostic Port Probe")
    log("=" * 60)
    
    # 1. Probe COM7 (DIAG) with binary protocol
    try_port(DIAG_PORT, 115200, "SPRD Binary DIAG", [SPRD_PING, SPRD_VER], binary=True)
    
    # 2. Probe COM7 with text commands
    try_port(DIAG_PORT, 115200, "SPRD Text DIAG", TEXT_CMDS, binary=False)
    
    # 3. Probe COM8 (AT) at different baud rates - without write timeout
    for baud in [9600, 115200, 57600]:
        try:
            ser = serial.Serial(AT_PORT, baudrate=baud, timeout=2)
            ser.reset_input_buffer()
            log(f"\n--- Testing AT port COM8 @ {baud} ---")
            for cmd in [b"AT\r\n", b"ATI\r\n", b"AT+CGMR\r\n"]:
                try:
                    ser.write(cmd)
                    time.sleep(0.5)
                    resp = ser.read(512)
                    label_cmd = cmd.decode().strip()
                    if resp:
                        log(f"  {label_cmd} => {resp.decode('utf-8', errors='replace').strip()}")
                    else:
                        log(f"  {label_cmd} => no response")
                except Exception as e:
                    log(f"  {cmd} => error: {e}")
            ser.close()
        except Exception as e:
            log(f"  COM8 @ {baud}: {e}")
    
    # Save results
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(results))
    
    log(f"\nResults saved to: {LOG_FILE}")

if __name__ == "__main__":
    main()
