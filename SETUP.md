# Athena Setup & Dependency Guide

This guide walks you through downloading and setting up all external requirements for Athena, including **Python**, **Ollama (Gemma)**, **FFmpeg**, **Whisper**, and **Piper Text-to-Speech**.

---

## 1. Python 3.12+

Athena is built on Python. 

### Windows Installation:
1. Download Python 3.12 or newer from the [Official Python Downloads Page](https://www.python.org/downloads/).
2. Run the installer.
3. **CRITICAL**: Make sure to check the box for **"Add python.exe to PATH"** before clicking "Install Now".
4. Open a new terminal (Command Prompt or PowerShell) and run:
   ```cmd
   python --version
   ```

---

## 2. Local LLM Setup (Ollama & Gemma)

Athena can fall back to local LLMs when the cloud API is offline.

1. Download and install Ollama from [ollama.com](https://ollama.com).
2. Open your terminal and start Ollama by pulling your preferred local model (Athena defaults to `gemma3:4b`):
   ```bash
   ollama run gemma3:4b
   ```
   *Tip: For low-spec or older hardware, you can use smaller models like `gemma:2b` or `gemma3:1b` and update the `OLLAMA_MODEL` in your `.env` file.*
3. Test that Ollama is responding locally by going to `http://localhost:11434` in your browser.

---

## 3. FFmpeg (Audio Conversion)

FFmpeg is required to convert audio files for speech-to-text (Whisper) and text-to-speech (Piper).

### Windows:
1. Download a pre-compiled build from [gyan.dev FFmpeg builds](https://www.gyan.dev/ffmpeg/builds/) (choose `ffmpeg-git-full.7z` or `ffmpeg-release-essentials.zip`).
2. Extract the folder to a safe place (e.g., `C:\ffmpeg`).
3. Add the `C:\ffmpeg\bin` directory to your system's **Environment Variables PATH**:
   - Press the Win key, search for "Edit the system environment variables", and click it.
   - Click **Environment Variables...**.
   - Under *System variables*, select **Path** and click **Edit...**.
   - Click **New** and add `C:\ffmpeg\bin`.
   - Click **OK** to save and close all windows.
4. Verify by opening a new terminal and running:
   ```cmd
   ffmpeg -version
   ```

---

## 4. Voice-to-Text (Whisper)

Athena uses OpenAI's Whisper model to transcribe voice messages.

**Do you need to download anything?**
No! The Whisper library installed via `pip` handles this automatically. On the very first voice message the bot receives, it will automatically download the configured model (defaults to `base`) and cache it in your user profile cache directory (under `~/.cache/whisper/`).

---

## 5. Text-to-Speech (Piper Voice Synthesis)

To enable voice replies from Athena, you need the **Piper** executable and a voice model.

### Step A: Download the Piper Executable
1. Go to the [Piper Github Releases Page](https://github.com/rhasspy/piper/releases).
2. Download the compressed file matching your OS (for Windows: `piper_windows_amd64.zip`).
3. Extract it to a folder on your computer (e.g. `C:\piper`).

### Step B: Download a Voice Model
1. Go to the [Piper Voice Catalogue](https://github.com/rhasspy/piper/blob/master/VOICES.md).
2. Select a voice (e.g. `en_US-amy-medium`).
3. Download **both** the `.onnx` file and its corresponding `.onnx.json` file:
   - `en_US-amy-medium.onnx`
   - `en_US-amy-medium.onnx.json`
4. Put these two files in a folder on your computer (e.g. `C:\piper\voices`).

### Step C: Configure your `.env` File
Enable voice replies and provide the full paths to the files you downloaded:
```env
VOICE_REPLIES_ENABLED=True
PIPER_EXECUTABLE=C:\piper\piper.exe
PIPER_MODEL_PATH=C:\piper\voices\en_US-amy-medium.onnx
```
*(Make sure to use correct paths pointing to where you extracted and saved the files on your machine).*
