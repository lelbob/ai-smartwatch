# Athena AI Smartwatch Deployment Guide

Complete step-by-step instructions to configure your computer and smartwatch for direct Telegram Bot AI messaging over SIM cellular data.

---

## 1. Computer Setup (Athena Telegram AI Listener)

1. **Set your Telegram Bot Token & Chat ID**:
   Create a bot with [@BotFather](https://t.me/BotFather) on Telegram and copy the Bot Token.

2. **Start Athena Bot Service**:
   ```bash
   python athena/main.py
   ```
   *Your computer is now listening to your Telegram Bot. Any voice or text messages sent from your smartwatch will be processed by Athena AI and replied to automatically!*

---

## 2. Smartwatch Setup (Native C Application)

1. **Flash C App to Smartwatch**:
   Run the automated flashing injector tool:
   ```bash
   python smartwatch_tools/mocor_app/flash_to_smartwatch.py
   ```

2. **Hardware Side Button Gestures**:
   - **Short Press Side Button**: Opens the watch display to **Screen 1** (Time, Tasks, 1, 2, 3 list).
   - **Hold Side Button**: Enters **Screen 2** (`Listening`) and records your voice message for as long as you hold down the button.
   - **Release Side Button**: Automatically stops recording, packages your voice message, and transmits it over your **SIM card cellular data** to your Telegram Bot!

3. **Incoming AI Reply Options**:
   - **Screen 3** displays your **Question** and the AI **Ans**.
   - Press **`[Read Aloud]`** to hear the answer spoken out loud.
   - Press **`[OK]`** to acknowledge and return directly to **Screen 1 (Tasks List)**.

---

## 3. Web Application & Visual Simulator

You can also test and demo the smartwatch GUI interface on your computer browser at any time:
```bash
python -m http.server 8080
```
👉 Open: `http://localhost:8080`
