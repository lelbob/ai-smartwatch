"""
full_firmware_extractor.py - Automated full 16MB NOR Flash extraction
from a LIVE running UNISOC SC6531 smartwatch over USB.

Tries 3 software-only methods in sequence (no hardware touching):
  1. DIAG mode-switch commands (0x0A) to trigger BootROM
  2. AT modem reset commands (AT+CFUN=1,1) to force SoC reboot
  3. USB bus reset to force re-enumeration

Then catches PID 0x4D00 (BootROM) and runs spd_dump.exe to read 16MB.
"""

import subprocess
import usb.core
import usb.backend.libusb1
import time
import struct
import os
import sys
import threading

# ── Paths ──────────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SPD_DIR    = os.path.join(SCRIPT_DIR, "spd_dump")
SPD_DUMP   = os.path.join(SPD_DIR, "spd_dump.exe")
FDL_NOR    = os.path.join(SPD_DIR, "nor_fdl1.bin")
FDL_T117   = os.path.join(SPD_DIR, "t117_fdl1.bin")
DUMP_DIR   = os.path.join(SCRIPT_DIR, "dumps")
OUT_BIN    = os.path.join(DUMP_DIR, "firmware_16mb.bin")

DLL_PATH   = os.path.join(SPD_DIR, "libusb-1.0.dll")

# ── HDLC Protocol ─────────────────────────────────────────────────
def sprd_crc16(data: bytes) -> int:
    crc = 0
    for b in data:
        crc ^= b
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0x8408
            else:
                crc >>= 1
    return crc & 0xFFFF

def build_hdlc_frame(cmd_id: int, sub_cmd: int = 0, payload: bytes = b"") -> bytes:
    raw = bytes([cmd_id, sub_cmd]) + payload
    crc = sprd_crc16(raw)
    packet = raw + struct.pack("<H", crc)
    stuffed = bytearray()
    for b in packet:
        if b == 0x7E:
            stuffed.extend([0x7D, 0x5E])
        elif b == 0x7D:
            stuffed.extend([0x7D, 0x5D])
        else:
            stuffed.append(b)
    return bytes([0x7E]) + bytes(stuffed) + bytes([0x7E])

# ── USB Device Helpers ─────────────────────────────────────────────
def get_backend():
    return usb.backend.libusb1.get_backend(find_library=lambda x: DLL_PATH)

def find_live_device(backend):
    """Find device in Live OS mode (PID 0x3D00)."""
    return usb.core.find(idVendor=0x1782, idProduct=0x3D00, backend=backend)

def find_bootrom_device(backend):
    """Find device in BootROM mode (PID 0x4D00)."""
    return usb.core.find(idVendor=0x1782, idProduct=0x4D00, backend=backend)

# ── Method 1: DIAG Mode Switch ────────────────────────────────────
def method_1_diag_mode_switch(dev):
    """Send DIAG protocol mode-switch commands to trigger BootROM."""
    print("\n" + "=" * 60)
    print("  METHOD 1: DIAG Mode-Switch Commands")
    print("=" * 60)
    
    frames = [
        ("Download Mode (0x0A, 0x01)", build_hdlc_frame(0x0A, 0x01)),
        ("BootROM Mode  (0x0A, 0x00)", build_hdlc_frame(0x0A, 0x00)),
        ("Auto-Download (0x0A, 0x04)", build_hdlc_frame(0x0A, 0x04)),
        ("Normal Reset  (0x05, 0x00)", build_hdlc_frame(0x05, 0x00)),
        ("Mode Switch   (0x0A, 0x02)", build_hdlc_frame(0x0A, 0x02)),
        ("Mode Switch   (0x0A, 0x03)", build_hdlc_frame(0x0A, 0x03)),
        ("Mode Switch   (0x0A, 0x05)", build_hdlc_frame(0x0A, 0x05)),
    ]
    
    for ep_out in [0x02, 0x03]:
        print(f"\n  Sending on EP {hex(ep_out)}:")
        for label, frame in frames:
            try:
                dev.write(ep_out, frame, timeout=200)
                print(f"    ✓ Sent: {label}")
                time.sleep(0.15)
                
                # Check for response
                for ep_in in [0x82, 0x83]:
                    try:
                        resp = dev.read(ep_in, 2048, timeout=150)
                        if resp:
                            resp_bytes = bytes(resp)
                            print(f"      Response ({len(resp_bytes)}B): {resp_bytes[:32].hex()}")
                    except:
                        pass
            except usb.core.USBError as e:
                if "Entity not found" in str(e) or "No such device" in str(e):
                    print(f"    ⚡ Device disconnected after {label} — possible reboot!")
                    return True
                else:
                    print(f"    ✗ {label}: {e}")
            except Exception as e:
                print(f"    ✗ {label}: {e}")
    
    return False

# ── Method 2: AT Command Modem Reset ──────────────────────────────
def method_2_at_modem_reset(dev):
    """Send AT commands to trigger a modem/SoC reset."""
    print("\n" + "=" * 60)
    print("  METHOD 2: AT Command Modem Reset")
    print("=" * 60)
    
    at_commands = [
        b"AT+CFUN=1,1\r\n",        # Modem full reset (most reliable)
        b"AT+CFUN=0\r\n",           # Modem power down
        b"AT+CFUN=1\r\n",           # Modem power up
        b"AT+RESET\r\n",            # Direct reset
        b"AT+REBOOT\r\n",           # Reboot command
        b"AT+POWEROFF\r\n",         # Power off
        b"AT+POWERDOWN\r\n",        # Power down
        b"AT+SPAT=0\r\n",           # Spreadtrum AT mode
        b"AT+DOWNLOAD\r\n",         # Try download mode
        b"AT+ENTERDL\r\n",          # Enter download
        b"AT+UPGRADEDOWNLOAD\r\n",  # Upgrade download mode
        b"AT+SPDDOWNLOAD\r\n",      # SPD download
        b"AT*SWRESET\r\n",          # Software reset
        b"AT+SPRDMEMREAD=0x80000000,256\r\n",  # Try direct memory read
    ]
    
    for ep_out in [0x02, 0x03]:
        print(f"\n  Sending on EP {hex(ep_out)}:")
        
        for at_cmd in at_commands:
            cmd_name = at_cmd.decode().strip()
            
            # Send raw AT command directly
            try:
                dev.write(ep_out, at_cmd, timeout=200)
                print(f"    ✓ Raw: {cmd_name}")
                time.sleep(0.1)
            except usb.core.USBError as e:
                if "No such device" in str(e):
                    print(f"    ⚡ Device disconnected after raw {cmd_name}!")
                    return True
            except:
                pass
            
            # Also send via DIAG AT tunnel (command 0x38)
            try:
                frame = build_hdlc_frame(0x38, 0x00, at_cmd)
                dev.write(ep_out, frame, timeout=200)
                print(f"    ✓ DIAG tunnel: {cmd_name}")
                time.sleep(0.1)
            except usb.core.USBError as e:
                if "No such device" in str(e):
                    print(f"    ⚡ Device disconnected after tunneled {cmd_name}!")
                    return True
            except:
                pass
            
            # Read any responses
            for ep_in in [0x82, 0x83]:
                try:
                    resp = dev.read(ep_in, 2048, timeout=100)
                    if resp:
                        text = bytes(resp).decode('ascii', errors='replace').strip()
                        if text and len(text) < 200:
                            print(f"      Response: {text[:80]}")
                except:
                    pass
    
    return False

# ── Method 3: USB Bus Reset ───────────────────────────────────────
def method_3_usb_bus_reset(dev):
    """Force USB bus reset to trigger device re-enumeration."""
    print("\n" + "=" * 60)
    print("  METHOD 3: USB Bus Reset")
    print("=" * 60)
    
    try:
        print("  Sending USB bus reset...")
        dev.reset()
        print("  ✓ USB bus reset sent")
        return True
    except usb.core.USBError as e:
        if "No such device" in str(e) or "Entity not found" in str(e):
            print("  ⚡ Device disconnected during reset — possible reboot!")
            return True
        print(f"  ✗ USB reset error: {e}")
    except Exception as e:
        print(f"  ✗ USB reset error: {e}")
    
    return False

# ── BootROM Catcher & spd_dump Runner ─────────────────────────────
def poll_for_bootrom(backend, timeout_sec=30):
    """Poll USB bus for PID 0x4D00 (BootROM) device."""
    print(f"\n  ⏳ Polling for BootROM (PID 0x4D00) for {timeout_sec}s...")
    start = time.time()
    poll_count = 0
    
    while time.time() - start < timeout_sec:
        try:
            dev = find_bootrom_device(backend)
            if dev is not None:
                elapsed = time.time() - start
                print(f"\n  🎯 BootROM DETECTED after {elapsed:.1f}s! (Poll #{poll_count})")
                return True
        except:
            pass
        
        poll_count += 1
        time.sleep(0.05)  # 50ms poll interval = 20 checks/sec
    
    print(f"  ✗ No BootROM detected after {timeout_sec}s ({poll_count} polls)")
    return False

def run_spd_dump():
    """Run spd_dump.exe to extract full 16MB flash."""
    print("\n" + "=" * 60)
    print("  RUNNING spd_dump.exe — FULL 16MB FLASH EXTRACTION")
    print("=" * 60)
    
    os.makedirs(DUMP_DIR, exist_ok=True)
    
    # Try both FDL loaders with their respective addresses
    configs = [
        (FDL_NOR,  "nor_fdl1.bin",  "0x34000000"),  # SC6531DA
        (FDL_T117, "t117_fdl1.bin", "0x40004000"),  # SC6531E
    ]
    
    for fdl_path, fdl_name, fdl_addr in configs:
        if not os.path.exists(fdl_path):
            print(f"  ⚠ {fdl_name} not found, skipping")
            continue
        
        print(f"\n  Trying loader: {fdl_name} @ {fdl_addr}")
        
        cmd = [
            SPD_DUMP,
            "--wait", "20",
            "fdl", fdl_path, fdl_addr,
            "read_flash", "0x80000000", "0", "0x1000000", OUT_BIN,
        ]
        
        print(f"  Command: {' '.join(cmd)}")
        print(f"  Output:  {OUT_BIN}")
        print(f"\n  Running (this may take several minutes)...")
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=SPD_DIR,
                timeout=300,  # 5 minute timeout
            )
            
            print(f"\n  STDOUT: {result.stdout.strip()[:500]}")
            if result.stderr:
                print(f"  STDERR: {result.stderr.strip()[:500]}")
            
            if os.path.exists(OUT_BIN):
                size = os.path.getsize(OUT_BIN)
                if size > 100000:  # More than 100KB = success
                    size_mb = size / (1024 * 1024)
                    print(f"\n  ╔══════════════════════════════════════════════════╗")
                    print(f"  ║  ✅ FIRMWARE EXTRACTION SUCCESSFUL!              ║")
                    print(f"  ║  File: {OUT_BIN}")
                    print(f"  ║  Size: {size:,} bytes ({size_mb:.2f} MB)")
                    print(f"  ╚══════════════════════════════════════════════════╝")
                    return True
                else:
                    print(f"  ⚠ Output file too small ({size} bytes), trying next loader...")
                    os.remove(OUT_BIN)
        except subprocess.TimeoutExpired:
            print("  ✗ spd_dump timed out after 5 minutes")
        except Exception as e:
            print(f"  ✗ spd_dump error: {e}")
    
    return False

# ── Main Orchestrator ──────────────────────────────────────────────
def main():
    print("╔══════════════════════════════════════════════════════════╗")
    print("║  UNISOC SC6531 FULL 16MB FIRMWARE EXTRACTOR             ║")
    print("║  Software-only — no hardware touching required          ║")
    print("╚══════════════════════════════════════════════════════════╝")
    
    # Preflight checks
    if not os.path.exists(SPD_DUMP):
        print(f"\n[ERROR] spd_dump.exe not found at: {SPD_DUMP}")
        return False
    
    if not os.path.exists(DLL_PATH):
        print(f"\n[ERROR] libusb-1.0.dll not found at: {DLL_PATH}")
        return False
    
    backend = get_backend()
    os.makedirs(DUMP_DIR, exist_ok=True)
    
    # ── Check if already in BootROM mode ──
    print("\n[Phase 0] Checking current USB state...")
    bootrom = find_bootrom_device(backend)
    if bootrom is not None:
        print("  🎯 Device ALREADY in BootROM mode (PID 0x4D00)!")
        return run_spd_dump()
    
    live = find_live_device(backend)
    if live is None:
        print("  ✗ No UNISOC device found (neither PID 0x3D00 nor 0x4D00)")
        print("  → Make sure the smartwatch is plugged in via USB")
        return False
    
    print(f"  ✓ Live OS device found (PID 0x3D00)")
    print(f"    Bus {live.bus}, Address {live.address}")
    
    # ── Try each software method ──
    methods = [
        ("Method 1", method_1_diag_mode_switch),
        ("Method 2", method_2_at_modem_reset),
        ("Method 3", method_3_usb_bus_reset),
    ]
    
    for method_name, method_func in methods:
        # Re-find device (may have changed after previous method)
        dev = find_live_device(backend)
        if dev is None:
            # Device disappeared — might be rebooting!
            print(f"\n  ⚡ Device not in Live OS mode — checking for BootROM...")
            if poll_for_bootrom(backend, timeout_sec=15):
                return run_spd_dump()
            
            # Wait for it to come back
            print("  Waiting for device to re-appear...")
            for _ in range(30):
                time.sleep(0.5)
                dev = find_live_device(backend)
                if dev:
                    print("  ✓ Device re-appeared in Live OS mode")
                    break
                br = find_bootrom_device(backend)
                if br:
                    print("  🎯 Device appeared in BootROM mode!")
                    return run_spd_dump()
            
            if dev is None:
                print("  ✗ Device did not re-appear")
                continue
        
        # Run the method
        device_disconnected = method_func(dev)
        
        # Poll for BootROM after each method
        if device_disconnected or True:  # Always poll
            if poll_for_bootrom(backend, timeout_sec=20):
                return run_spd_dump()
    
    # ── All software methods exhausted ──
    print("\n" + "=" * 60)
    print("  ALL SOFTWARE METHODS ATTEMPTED")
    print("=" * 60)
    print("""
  None of the software triggers caught the BootROM.
  This means the Mocor OS firmware on your watch does NOT
  have the DIAG mode-switch handler enabled.

  ┌─────────────────────────────────────────────────┐
  │  PHYSICAL METHOD (Last Resort):                 │
  │                                                 │
  │  1. Unplug the USB cable                        │
  │  2. Hold the side button until watch powers off  │
  │  3. Keep holding the side button                │
  │  4. While holding, plug in the USB cable        │
  │  5. Hold for 3 seconds, then release            │
  │  6. Run this script again immediately           │
  └─────────────────────────────────────────────────┘
    """)
    
    # One more poll attempt in case the user does the button method
    print("  Waiting 30 seconds in case you try the button method now...")
    if poll_for_bootrom(backend, timeout_sec=30):
        return run_spd_dump()
    
    return False

if __name__ == "__main__":
    success = main()
    if success:
        print("\n🎉 Firmware extraction complete!")
    else:
        print("\n⚠ Firmware extraction was not successful this run.")
    
    input("\nPress Enter to exit...")
