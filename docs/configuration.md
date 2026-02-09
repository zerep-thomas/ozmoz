# Configuration Guide

Ozmoz supports a hybrid configuration, allowing users to prioritize either data privacy (Local) or performance speed (Cloud).

## 1. Transcription Engine Selection

Select the engine that best fits your hardware capabilities and privacy requirements.

| Feature     | Local Model (Whisper)        | Cloud API (Groq/Deepgram)  |
| :---------- | :--------------------------- | :------------------------- |
| **Privacy** | 100% Offline (On-Device)     | Data processed by provider |
| **Latency** | Hardware Dependent (GPU/CPU) | Ultra-low (Sub-second)     |
| **Cost**    | Free                         | Free tier / Pay-as-you-go  |
| **Setup**   | ~1.8 GB Download             | API Key Required           |

---

### Option A: Local Model (Offline)

_Recommended for privacy-conscious users._

1.  Navigate to **Settings > General**.
2.  In the Model dropdown, select **Whisper V3 Turbo**.

<div align="center">
  <img src="images/app1.png" alt="Select Local Model" width="75%" style="border-radius: 8px; border: 1px solid #30363d;">
</div>

3.  Click the **Download** button.
    - **Note:** This process requires downloading approximately **1.8 GB** of model weights. Ensure a stable connection. Once completed, the model operates entirely offline.

<div align="center">
  <img src="images/app2.png" alt="Download Progress" width="75%" style="border-radius: 8px; border: 1px solid #30363d;">
</div>

---

### Option B: Cloud APIs (High Performance)

_Recommended for maximum speed and advanced capabilities._

1.  Obtain an API key from a supported provider:
    - [Groq Cloud](https://groq.com/) (Recommended for LLM & Transcription)
    - [Deepgram](https://deepgram.com/) (Specialized Speech-to-Text)
2.  Navigate to **Settings > API Keys** and input your credentials.

> **Security Note:** Ozmoz automatically masks your keys (`********`) and uses local encryption for storage. Keys are never transmitted.

<div align="center">
  <img src="images/app3.png" alt="API Key Management" width="75%" style="border-radius: 8px; border: 1px solid #30363d;">
</div>

---

## 2. Operation

Once configured, the main interface allows for rapid switching between models. You can verify the active status in the dashboard.

<div align="center">
  <img src="images/app4.png" alt="Ozmoz Interface" width="75%" style="border-radius: 8px; border: 1px solid #30363d;">
  <br><br>
  
  [**View Hotkeys & Controls →**](features/shortcuts.md)
</div>
