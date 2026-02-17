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

Ozmoz stands on the shoulders of focused, high-quality open-source projects that make lightweight desktop AI integration possible.

### Core & Desktop Integration

- **pywebview** – Lightweight bridge between Python and native WebView2, enabling a modern HTML interface without Electron-level overhead.
- **pystray** – Minimal system tray integration with a tiny footprint.
- **pywin32** – Low-level Windows API access for focus management and native interaction.

### Speech & Audio Engine

- **faster-whisper** / **CTranslate2** – High-performance local Whisper inference optimized for CPU/GPU deployment.
- **PyCaw** – Direct control of the Windows Core Audio API for smart muting automation.
- **FFmpeg** – Universal audio processing backbone.

### Vision & Interaction

- **python-mss** – Extremely fast screen capture used for multimodal Vision features.
- **text2num** – Smart spoken-number normalization for accurate dictation output.

### AI Infrastructure

- **Groq** – LPU-accelerated inference APIs.
- **Deepgram** – Cloud speech models (Nova series).
- **Cerebras** – Wafer-scale AI compute infrastructure.

## License

This project is distributed under the **Apache License 2.0**.
Bundled dependencies (FFmpeg, Qt, etc.) are subject to their respective licenses as detailed in the `LICENSE` file.

<div align="center">
  <br>
  <p>&copy; 2026 Ozmoz Project</p>
</div>
```
