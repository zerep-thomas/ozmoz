# Ozmoz

**The fastest speech-to-text app for Windows.**

Ozmoz is a Windows application that allows you to transcribe speech to text ultra-fast, either in the cloud (with Groq) or locally, whether you have a powerful computer or not. You just need to hold down `Ctrl + Space` and your words will appear in any text field.

## Why Ozmoz?

Ozmoz was created to meet the need for speed and privacy for users, especially students, to facilitate note-taking.

- **Free**: Accessible to everyone, with no time limits.
- **Open Source**: Everyone can use and modify it.
- **Private**: Your data stays on your computer when using local models.
- **Simple**: An interface and features designed to be simple and fast.

## How It Works

1. **Press** `Ctrl + Space` and hold it down to start recording.
2. **Speak** your words while the shortcut is active.
3. **Release** the shortcut. Ozmoz processes your speech using Whisper.
4. **Get** your transcribed text pasted directly into whatever app you are using.

The process can be done in the cloud via Groq if you need extreme speed, or locally if you want better confidentiality. In both cases, OpenAI's Whisper models are used.

## Features

- **Global Push-to-Talk**: Use `Ctrl + Space` anywhere in Windows to start dictating.
- **Cloud Transcription**: Uses Groq's API for near-instant results with `Whisper V3` and `Whisper V3 Turbo`.
- **Local Transcription**: Runs `Faster-Whisper` entirely offline on your CPU or GPU. Models (Base, Small, Turbo, Distil) can be downloaded directly from the app's interface.
- **Custom Modes**: Create presets tailored to your workflow. For example, the "Email Draft" mode automatically formats your speech into a structured professional email with greetings and sign-offs.
- **History & Statistics**: Keep track of your past transcriptions, view detailed stats (words per minute, time saved), and search through your history.
- **Custom Vocabulary**: Add specific names, acronyms, or industry terms to improve transcription accuracy.
- **System Tray Integration**: Runs quietly in the background and can be opened with a single click.

## Quick Start

### Installation

1. Download the latest release from the [releases page](https://github.com/zerep-thomas/ozmoz/releases).
2. Extract the `.zip` file anywhere on your computer.
3. Launch `ozmoz.exe`.
4. (Optional) Go to Settings to enter your Groq API key for cloud transcription, or download a local model.
5. Start talking!

> **Note on Antivirus**: Because Ozmoz uses global keyboard shortcuts and modifies the clipboard to paste text, some overly aggressive antiviruses (like Windows Defender occasionally) might flag it. You may need to add an exception for the `ozmoz.exe` folder.

## Development Setup

If you want to run Ozmoz from source or contribute to the project:

### Prerequisites

- Python 3.10+
- FFmpeg (must be installed and in your system PATH, or placed in the root directory)

### Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/zerep-thomas/ozmoz.git
   cd ozmoz
   ```
2. Create and activate a virtual environment:
   ```bash
   python -m venv venv
   venv\Scripts\activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Run the application:
   ```bash
   python run.py
   ```

### Building from Source

To compile the application into a standalone `.exe` using PyInstaller:

1. Ensure `ffmpeg.exe` and `ffprobe.exe` are in the root directory.
2. Run the following command:
   ```bash
   pyinstaller ozmoz.spec --noconfirm
   ```
3. The compiled application will be available in the `dist/ozmoz/` folder.

## Architecture

Ozmoz is built as a native Windows application combining:

- **Frontend/UI**: PySide6 (Qt for Python) with QML for a hardware-accelerated, fluid interface.
- **Backend**: Python for system integration, audio processing, and API communication.
- **Core Libraries**:
  - `faster-whisper`: Local speech recognition with CTranslate2 optimization.
  - `groq`: Cloud speech recognition API.
  - `PyAudio` & `pydub`: Audio capture and processing.
  - `pynput` & `win32gui`: Global hotkeys and active window management.
  - `win32crypt`: Secure DPAPI encryption for API keys.

## Known Issues & Limitations

This project is actively being developed. We believe in transparency about its current state:

- **Windows Only**: Ozmoz currently relies heavily on Windows APIs (`win32gui`, `win32crypt`, `winsound`) for clipboard management, hotkeys, and secure credential storage. It is not compatible with macOS or Linux.
- **First-Run Local Models**: Downloading local models (especially the Turbo or Large models) can take several minutes depending on your internet connection.
- **Email Draft Formatting**: While the "Email Draft" mode uses advanced semantic structuring to format emails across multiple languages, it does not use an LLM, so complex instructions might not be perfectly formatted.

We're actively working on several features and improvements. Contributions and feedback are welcome!

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Acknowledgments

- **OpenAI** for the Whisper speech recognition models.
- **Systran** and the `faster-whisper` team for the optimized inference engine.
- **Groq** for their fast cloud inference API.
- **Qt/QML** for the powerful UI framework.
