# ⌚ Athena — AI Smartwatch & Firmware Toolkit

A privacy-focused, voice-first personal assistant and hardware reverse-engineering toolkit designed for smartwatches and wearable devices.

Athena runs as a Telegram bot for hands-free voice commands (reminders, tasks, notes, SearXNG search, and Piper TTS replies) combined with custom firmware tools to communicate directly with UNISOC SC6531-based smartwatches.

---

## ⚡ Features

### 🤖 Voice Assistant Engine (Athena Bot)
- **Smart Reminders**: Timezone-aware natural language scheduling ("Remind me next Friday at 5pm").
- **Task & Memory Management**: Manage tasks, notes, and personal facts hands-free.
- **Daily Briefing**: Weather, upcoming tasks, and web search powered by Gemini & SearXNG.
- **Voice IO**: Speech-to-text (Whisper) and audio replies (Piper TTS).
- **Proactive Nudges**: Automated notifications when tasks or reminders are due.

### 🛠️ Smartwatch Hardware & Firmware Toolkit
- **Target Hardware**: UNISOC / Spreadtrum SC6531 smartwatch (Model R36C / 3G Electronics).
- **Direct WinUSB Communication**: Native Python engine (`pyusb`) communicating over USB Endpoints `0x02` & `0x82` (Configuration 3).
- **Firmware Dumper (`full_flash_dumper.py`)**: Extract raw NOR flash binary (`firmware_dump.bin`).
- **Hardware Telemetry Streamer (`winusb_dump_nv.py`)**: Live reader for I2C sensors (`0x20`, `0x21`, `0x28`), SDIO WiFi logs, battery voltage, and signal levels.

---

## 📁 Project Structure

```
ai-smartwatch/
├── SMARTWATCH_DOCUMENTATION.txt  # Complete technical specifications & diagram UI docs
├── PROJECT_LOG.txt               # Detailed log of all research, working methods & failed attempts
├── index.html                    # 240x240 smartwatch web display simulator
├── styles.css                    # OLED dark mode theme & diagram layout CSS
├── app.js                        # Hold/release gesture engine & SIM Telegram client
├── athena/                       # Core AI Telegram bot & LLM tool router
│   ├── main.py             # Bot entry point
│   ├── telegram_bot.py     # Telegram handlers
│   ├── reminders.py        # Reminder parsing & scheduling
│   ├── model_router.py     # Model fallback router
│   └── database.py         # SQLite persistence layer
├── smartwatch_tools/             # Hardware reverse-engineering & flashing tools
│   ├── full_firmware_extractor.py # Automated multi-method 16MB flash dumper
│   ├── dumps/                    # Firmware binaries (52KB memory, 10.5KB NVRAM)
│   ├── mocor_app/                # Native C smartwatch application & flash injector
│   └── spd_dump/                 # Spreadtrum BootROM tools & FDL loaders
```

---

## 🚀 Quick Setup Guide

### 1. Installation & Environment
```bash
git clone https://github.com/lelbob/ai-smartwatch.git
cd ai-smartwatch
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Environment Configuration
Copy `.env.example` to `.env` and enter your keys:
```env
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
GEMINI_API_KEY=your_gemini_api_key
ATHENA_LOCATION=Your City, Country
```

### 3. Firmware Dumper Usage
1. Connect the smartwatch via Micro-USB.
2. Launch `tools/zadig.exe` → Options → List All Devices → Select **Coolsand (Interface 0)** & **Coolsand (Interface 1)** → **Replace Driver with WinUSB**.
3. Run the dumper script:
   ```bash
   python full_flash_dumper.py
   ```

### 4. Running the Bot
```bash
python -m athena.main
```

---

## 📜 License
MIT License.
