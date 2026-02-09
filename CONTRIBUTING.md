# Contributing to Ozmoz

Thank you for your interest in contributing to Ozmoz! We welcome pull requests, bug reports, and feature suggestions.

## Development Environment Setup

Ozmoz is built with Python 3.10+ and uses `pywebview` for the frontend. Follow these steps to set up your local environment.

### Prerequisites

- **Python 3.10** or higher.
- **Node.js** (Optional, only if modifying complex frontend assets, though standard JS is currently used).
- **Visual Studio C++ Build Tools** (Required for compiling certain Python dependencies on Windows).

### Step-by-Step Guide

1.  **Clone the Repository**

    ```bash
    git clone [https://github.com/zerep-thomas/ozmoz.git](https://github.com/zerep-thomas/ozmoz.git)
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

## Coding Standards

- **Python:** We use `black` for formatting and `isort` for import sorting. Please type-hint your code (`typing` module).
- **JavaScript:** Use modern ES6+ syntax.
- **Logging:** Use the `logging` module, not `print()`.

## Submitting Changes

1.  **Fork** the repo on GitHub.
2.  **Clone** the project to your own machine.
3.  **Commit** changes to your own branch.
4.  **Test** your changes on Windows (primary support target).
5.  **Push** your work back up to your fork.
6.  Submit a **Pull Request** so that we can review your changes.

**Note:** Please do not modify the version number in `src/modules/config.py` unless you are preparing a release.
