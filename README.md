<div align="center">
  <img src="docs/images/banner.png" alt="Ozmoz Banner" width="100%">

<p>
  <br><br>
<p>
  <a href="https://www.python.org/">
    <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python Version">
  </a>
  <a href="https://github.com/zerep-thomas/ozmoz/releases">
    <img src="https://img.shields.io/badge/Windows-10%20%7C%2011-0078D6?style=for-the-badge&logo=windows&logoColor=white" alt="Platform">
  </a>
  <a href="https://pywebview.flowrl.com/">
    <img src="https://img.shields.io/badge/GUI-PyWebView-orange?style=for-the-badge&logo=html5&logoColor=white" alt="GUI Framework">
  </a>
  <a href="https://creativecommons.org/licenses/by-nc-sa/4.0/">
    <img src="https://img.shields.io/badge/License-CC%20BY--NC--SA%204.0-green?style=for-the-badge" alt="License">
  </a>
  <a href="docs/docs.md">
    <img src="https://img.shields.io/badge/Docs-Read%20Documentation-blueviolet?style=for-the-badge&logo=readthedocs&logoColor=white" alt="Read Documentation">
  </a>
  <a href="https://www.instagram.com/ozmoz.ai/" target="_blank">
    <img src="https://img.shields.io/badge/Instagram-Follow%20Us-E4405F?style=for-the-badge&logo=instagram&logoColor=white" alt="Follow on Instagram">
  </a>
</p>

<br>
<br>

<a href="https://github.com/zerep-thomas/ozmoz/releases/latest">
  <img src="https://img.shields.io/github/v/release/zerep-thomas/ozmoz?style=for-the-badge&label=DOWNLOAD&logo=windows&logoColor=white" alt="Download Ozmoz">
</a>

</div>

<br>

## 📖 Overview

**Ozmoz** is a desktop application that integrates AI into the Windows operating system. Unlike web-based chat interfaces, Ozmoz floats above your applications, allowing you to interact with AI models (Groq, Cerebras) and high-speed transcription engines without interrupting your workflow. It supports both **Cloud** (API) and **Local** (Offline) processing.
<br>

<div align="center">
  <img src="docs/images/demo.webp" alt="Demo">
</div>

## ✨ Key Features

- **🎙️ Flexible Transcription:**
  - **Local Mode:** Uses _Whisper V3 Turbo_ running on your device (Offline, Privacy-focused). Optimized for NVIDIA GPUs (CUDA) with CPU fallback.
  - **Cloud Mode:** Uses _Groq/Whisper_ or _Deepgram Nova-2_ for ultra-low latency.
- **🧠 Contextual AI:** Select text in any application, press a keyboard shortcut, and Ozmoz analyzes it using the latest LLMs.
- **👁️ Screen Vision:** Allows AI to “see” your active window to explain code, analyze data, or summarize (multimodal).
- **🌐 Live Web Search:** Performs real-time internet searches to provide up-to-date answers with citations.
- **🤖 Custom Agents:** Create specialized characters triggered by voice keywords (e.g., “Hey Dev” to switch to a coding assistant).
- **⚡ Smart Replacements:** Built-in text expander for frequently used phrases.
- **📊 Analytics Dashboard:** Tracks dictated words, time saved, and typing speed (WPM).

<br>

## 🛠️ Tech Stack

A hybrid architecture chosen for high performance and low memory footprint.

- **Core:** Python 3.10+ (AI Orchestration & Backend Logic).
- **Local Inference:** `faster-whisper` (CTranslate2) with portable CUDA support.
- **GUI Bridge:** `pywebview` (Wraps native Edge WebView2).
- **Frontend:** HTML5, CSS3, Modern JavaScript (ES6 Modules).
- **Charts & Visualization:** `Chart.js` with `chartjs-plugin-datalabels`.
- **OS Integration:** `pywin32` & `ctypes` (Low-level Hooks), `mss` (Screen Capture), `keyboard` (Hotkeys).
- **Utilities:** `fuse.js` (Fuzzy Search), `markdown-it` (Rendering).

<br>

## 🚀 Installation

### Prerequisites

Before running Ozmoz, ensure you have the following installed:

- **Windows 10/11**
- **Python 3.10** or higher
- **FFmpeg & zlibwapi.dll** (Must be placed in a `/bin` folder at the root for local features).

### Setup Guide

1.  **Clone the repository**

    ```bash
    git clone https://github.com/ton-profil/ozmoz.git
    cd ozmoz
    ```

2.  **Create a Virtual Environment**

    ```bash
    python -m venv venv
    .\venv\Scripts\activate
    ```

3.  **Install Dependencies**

    ```bash
    pip install -r requirements.txt
    ```

4.  **Run the Application**
    ```bash
    python app.py
    ```

<br>

## ⚙️ Configuration

Ozmoz is hybrid. You can use it **100% offline for transcription**, or add API keys for AI generation and cloud speed.

| Provider         | Purpose                                           | Requirement         |
| :--------------- | :------------------------------------------------ | :------------------ |
| **Groq API**     | Text generation (LLM) & Cloud transcription.      | **Required for AI** |
| **Local Model**  | _Whisper V3 Turbo_ (Offline transcription).       | **No Key Required** |
| **Deepgram API** | _Nova-2_ model (Alternative cloud transcription). | Optional            |
| **Cerebras API** | High-throughput alternative for LLM tasks.        | Optional            |

> **Local Model Note:** Upon first use of the "Local" model, a ~1.8 GB download will occur.

<br>

## ⌨️ Controls & Hotkeys

| Action                   | Default Hotkey                   | Description                                                                            |
| :----------------------- | :------------------------------- | :------------------------------------------------------------------------------------- |
| **Start/Stop Dictation** | <kbd>Ctrl</kbd> + <kbd>X</kbd>   | Toggles the microphone. Transcription is automatically pasted at the cursor.           |
| **Ask AI**               | <kbd>Ctrl</kbd> + <kbd>Q</kbd>   | Analyze selected text or answer a voice command using the active LLM.                  |
| **Screen Vision**        | <kbd>Alt</kbd> + <kbd>X</kbd>    | Takes a screenshot of the active window and sends it to the Vision model for analysis. |
| **Web Search**           | <kbd>Alt</kbd> + <kbd>W</kbd>    | Performs a live web search based on your voice prompt or selection.                    |
| **Toggle UI**            | <kbd>Ctrl</kbd> + <kbd>Alt</kbd> | Hides or Shows the floating widget overlay.                                            |

<br>

## 🏗️ Building from Source

To create a standalone `.exe` file:

1.  Ensure `pyinstaller` is installed (`pip install pyinstaller`).
2.  Build using the spec file:
    ```bash
    pyinstaller Ozmoz.spec
    ```
3.  **Important:** Manually copy the `bin/` folder (containing ffmpeg and zlibwapi.dll) into the `dist/Ozmoz/` folder after building.

<br>

## 🤝 Contributing

1.  Fork the Project
2.  Create your Feature Branch
3.  Commit your Changes
4.  Push to the Branch
5.  Open a Pull Request

<br>

## 📄 License

Distributed under CC BY-NC-SA 4.0 License. See `LICENSE` for more information.
This project bundles:

- **FFmpeg** (LGPLv2.1)
- **zlibwapi** (zlib license)
- **Fuse.js** (Apache 2.0)
- **Markdown-it** (MIT)
- **Chart.js** & **chartjs-plugin-datalabels** (MIT)

<br/>

<div align="center">
  <p>
    Built with ❤️
  </p>
  <p>
    &copy; 2025 Ozmoz 
  </p>
</div>
