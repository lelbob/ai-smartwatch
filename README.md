# ⌚ Athena AI Smartwatch

A privacy-focused, voice-first AI personal assistant and hardware reverse-engineering toolkit for smartwatches and wearable devices.

Athena combines a hands-free personal assistant (reminders, tasks, notes, private web search) with custom firmware tools to communicate directly with UNISOC SC6531-based smartwatches.

---

## ⚡ Features

### 🤖 Voice Assistant Engine
- **Smart Reminders**: Timezone-aware scheduling ("Remind me next Friday at 5pm").
- **Tasks & Memory**: Manage tasks, notes, and personal facts with natural language.
- **Daily Briefing**: Weather, upcoming tasks, and web search powered by Gemini & SearXNG.
- **Voice Interface**: Speech-to-text (Whisper) and natural audio replies (Piper TTS).

### 🛠️ Hardware & Firmware Toolkit
- **Target Hardware**: UNISOC / Spreadtrum SC6531 smartwatch (Model R36C / 3G Electronics).
- **Direct WinUSB Communication**: Native Python engine (`pyusb`) communicating over USB Endpoints `0x02` & `0x82` (Configuration 3).
- **Firmware Dumper (`full_flash_dumper.py`)**: Extract raw NOR flash binary (`firmware_dump.bin`).
- **Hardware Telemetry Streamer (`winusb_dump_nv.py`)**: Live reader for I2C sensors (`0x20`, `0x21`, `0x28`), SDIO WiFi logs, battery voltage, and signal levels.

---

## 📁 Repository Layout

```
ai-smartwatch/
├── README.md               # Main project documentation
├── full_flash_dumper.py    # WinUSB direct firmware dumper
├── winusb_dump_nv.py       # Live hardware telemetry reader
├── probe_diag.py           # Diagnostic port prober
├── find_devices.py         # Registry USB device scanner
├── dumps/                  # Firmware & memory binaries
│   ├── firmware_dump.bin   # Dumped flash image
│   └── live_diag_stream.bin# Live hardware telemetry log
└── tools/                  # Drivers and flashing utilities
    ├── zadig.exe           # WinUSB driver installer
    └── spd_dump/           # Spreadtrum bootloader utilities & FDL loaders
```

---

## 🚀 Quick Setup Guide

### 1. Install Dependencies
```bash
python -m venv venv
venv\Scripts\activate
pip install pyusb libusb pyserial python-telegram-bot google-generativeai
```

### 2. Firmware Dumper Usage
1. Connect the smartwatch via Micro-USB.
2. Launch `tools/zadig.exe` → Options → List All Devices → Select **Coolsand (Interface 0)** & **Coolsand (Interface 1)** → **Replace Driver with WinUSB**.
3. Run the dumper script:
   ```bash
   python full_flash_dumper.py
   ```

---

## 📜 License & Acknowledgments
Licensed under MIT. Open-source reverse-engineering tools developed for wearable AI research.
