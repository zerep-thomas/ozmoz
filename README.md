<div align="center">
  <img src="docs/images/banner.png" alt="Ozmoz Banner" width="100%">
  <br><br>
  
  <a href="https://www.python.org/">
    <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python Version">
  </a>
  <a href="https://github.com/zerep-thomas/ozmoz/releases">
    <img src="https://img.shields.io/badge/Windows-10%20%7C%2011-0078D6?style=for-the-badge&logo=windows&logoColor=white" alt="Platform">
  </a>
  <a href="https://pywebview.flowrl.com/">
    <img src="https://img.shields.io/badge/GUI-PyWebView-orange?style=for-the-badge&logo=html5&logoColor=white" alt="GUI Framework">
  </a>
  <a href="LICENSE">
    <img src="https://img.shields.io/badge/License-Apache%202.0-blue?style=for-the-badge&logo=apache&logoColor=white" alt="License">
  </a>

<br><br>

  <a href="https://github.com/zerep-thomas/ozmoz/releases/latest">
    <img src="https://img.shields.io/github/v/release/zerep-thomas/ozmoz?style=for-the-badge&label=DOWNLOAD&logo=windows&logoColor=white" alt="Download Ozmoz">
  </a>
  <a href="docs/docs.md">
    <img src="https://img.shields.io/badge/Docs-Read%20Documentation-blueviolet?style=for-the-badge&logo=readthedocs&logoColor=white" alt="Read Documentation">
  </a>
</div>

<br>

## Overview

**Ozmoz** is a desktop integration tool designed to bridge the gap between Windows applications and Large Language Models (LLMs). It operates as a persistent overlay, enabling seamless access to speech-to-text engines and AI analysis without context switching.

The application supports a **hybrid architecture**, allowing users to choose between local privacy-focused processing (Whisper V3 Turbo) and high-performance cloud APIs (Groq, Deepgram).

<div align="center">

https://github.com/user-attachments/assets/b45938df-d0e1-41b0-89ad-bdb44e7931b3

</div>

## Key Features

- **Global Dictation:** System-wide voice transcription using local CUDA acceleration or low-latency cloud APIs.
- **Contextual Intelligence:** Analyze selected text in any application via global hotkeys.
- **Multimodal Vision:** Screen capture capabilities for AI-assisted troubleshooting, code explanation, and data extraction.
- **Web Search:** Real-time information retrieval with citation support.
- **Privacy & Security:** API keys and chat history are encrypted at rest. Full offline capability available.

## Technical Architecture

Ozmoz is engineered for minimal resource footprint while maintaining high performance:

- **Backend:** Python 3.10+ handling orchestration and logic.
- **Inference:** `faster-whisper` (CTranslate2) for local speech recognition.
- **Interface:** `pywebview` (Edge WebView2) for a responsive, modern GUI.
- **System Integration:** Low-level hooks via `pywin32` and `ctypes` for window management and input simulation.

## Installation

### Option 1 — Prebuilt Installer (Recommended)

1. Download the latest installer from the [Releases Page](https://github.com/zerep-thomas/ozmoz/releases).
2. Run `Ozmoz-Setup.exe`.
3. Follow the [Configuration Guide](docs/configuration.md) to set up your AI providers.

---

### Option 2 — Run from Source (Developers)

```bash
git clone https://github.com/zerep-thomas/ozmoz.git
cd ozmoz
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

## External Dependencies

### FFmpeg (Required)

Ozmoz relies on **FFmpeg** as a universal audio backend for format conversion and preprocessing.

FFmpeg is **not bundled** with the repository and must be installed separately.

#### Installation

- **Windows**
  - Download static builds from https://ffmpeg.org/download.html
  - Add `ffmpeg.exe` and `ffprobe.exe` to your system `PATH`

## Acknowledgements

This project stands on the shoulders of giants. We gratefully acknowledge the following open-source projects that make Ozmoz possible:

### Core & GUI

- [pywebview](https://pywebview.flowrl.com/) - A lightweight cross-platform wrapper to render the HTML/JS GUI.
- [pystray](https://github.com/moses-palmer/pystray) - System tray icon and menu integration, replacing heavier frameworks for a minimal footprint.
- [Pillow](https://python-pillow.org/) - Image processing library used for icon management and visual assets.
- [python-dotenv](https://github.com/theskumar/python-dotenv) - Configuration management via environment variables.

### System Integration (Windows)

- [pywin32](https://github.com/mhammond/pywin32) - Essential low-level hooks for window management, focus control, and native clipboard access.
- [pynput](https://github.com/moses-palmer/pynput) - Robust global hotkey monitoring (Press & Hold detection).
- [keyboard](https://github.com/boppreh/keyboard) & [PyAutoGUI](https://github.com/asweigart/pyautogui) - Simulation of keystrokes for the "Auto-Paste" and smart selection features.
- [pyperclip](https://github.com/asweigart/pyperclip) - Cross-platform clipboard text functions
- [Keyring](https://github.com/jaraco/keyring) - Secure storage of API keys using the Windows Credential Locker.
- [Cryptography](https://cryptography.io/en/latest/) - Fernet (AES) encryption implementation for securing local chat history at rest.

### Audio & Processing

- [Faster-Whisper](https://github.com/SYSTRAN/faster-whisper) / [CTranslate2](https://github.com/OpenNMT/CTranslate2) - The engine behind the local, offline speech recognition (Whisper V3 Turbo).
- [PyAudio](https://people.csail.mit.edu/hubert/pyaudio/) - Low-latency microphone input stream handling.
- [PyCaw](https://github.com/AndreMiras/pycaw) - Windows Core Audio API control for automatic system muting/unmuting.
- [NumPy](https://numpy.org/) - High-performance scientific computing for audio buffer manipulation.
- [Text-to-num](https://github.com/allo-media/text2num) - Post-processing utility to convert spoken numbers into digits.
- [FFmpeg](https://github.com/FFmpeg/FFmpeg) - Universal audio backend for format conversion.

### AI & Cloud Providers

- [Groq Python SDK](https://github.com/groq/groq-python) - Integration for LPU-accelerated inference (Llama 3, Whisper).
- [Deepgram Python SDK](https://github.com/deepgram/deepgram-python-sdk) - Integration for Nova-2/Nova-3 speech models.
- [Cerebras Cloud SDK](https://github.com/Cerebras/cerebras-cloud-sdk-python) - Integration for wafer-scale cluster inference.
- [Requests](https://requests.readthedocs.io/) - HTTP library handling updates and file downloads.

### Frontend & Visuals

- [MSS](https://github.com/BoboTiG/python-mss) - Ultra-fast, cross-platform screen capture for Vision capabilities.
- [Markdown-it](https://github.com/markdown-it/markdown-it) - Fast and compliant Markdown parsing for AI responses.
- [KaTeX](https://katex.org/) - Professional typesetting library for rendering mathematical notation.
- [Highlight.js](https://highlightjs.org/) - Syntax highlighting for generated code blocks.
- [Chart.js](https://github.com/chartjs/Chart.js) - Data visualization for the user activity dashboard.
- [Fuse.js](https://github.com/krisk/Fuse) - Powerful fuzzy-search implementation for logs and history filtering.
- [Open Sauce Sans](https://github.com/marcologous/Open-Sauce-Fonts) - Main application typography (SIL Open Font License).

## License

This project is distributed under the **Apache License 2.0**.
Bundled dependencies (FFmpeg, Qt, etc.) are subject to their respective licenses as detailed in the `LICENSE` file.

<div align="center">
  <br>
  <p>&copy; 2026 Ozmoz Project</p>
</div>
```
