# AI QA Agent for REST Endpoints

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Local web application for running test suite documents (`.docx`, `.pdf`, `.txt`, `.md`) or OpenAPI specs against REST/JSON endpoints automatically. A local LLM translates each test case into structured JSON, while HTTP execution and verification are deterministic.

## Table of Contents

- [Features](#features)
- [Architecture](#architecture)
- [Project Structure](#project-structure)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Usage](#usage)
  - [Web UI](#web-ui)
  - [CLI](#cli)
  - [OpenAPI Conversion](#openapi-conversion)
  - [Mock API](#mock-api)
- [Development](#development)
- [Testing](#testing)
- [Security](#security)
- [Contributing](#contributing)
- [License](#license)

## Features

- Upload test suite documents following the standard template.
- Convert OpenAPI JSON/YAML specs into test suite documents using a local LLM.
- Local LLM (LM Studio) extracts each test case into structured JSON.
- HTTP execution via `httpx` with support for `none` / `basic` / `bearer` / `api_key` auth.
- Deterministic verification: status code, schema narration, jsonpath, regex, contains.
- Clear test output with assertion-level details and LLM explanation for failed cases.
- Excel (`.xlsx`) report generated on demand; no reports stored inside the project folder.
- Clean web UI with loading animation and current test case progress.
- LLM configuration (base URL and model name) configurable per session in the UI.

## Architecture

```
input/adapter  ->  llm/parse  ->  runner/execute  ->  runner/verify  ->  llm/explain  ->  reporter
   (docx/pdf/txt/md)    (LLM)         (HTTP)         (deterministic)      (LLM, FAIL only)   (xlsx)
```

| Module | Responsibility |
|--------|----------------|
| `app/input/` | Document parsing, chunking, and test suite DOCX generation. |
| `app/llm/` | LLM provider, prompts, tolerant parsing, retry, OpenAPI converter. |
| `app/runner/` | HTTP executor, auth handler, assertions, verifier, reporter. |
| `app/agent/` | Thin orchestration nodes and pipeline graph. |
| `app/web/` | FastAPI routes, in-memory job store, static UI. |
| `app/cli.py` | Command-line runner. |
| `mock/` | FastAPI mock API and matching test suite for end-to-end testing. |

## Project Structure

```
.
├── app/
│   ├── agent/          # Pipeline orchestration nodes
│   ├── input/          # Document parsing and generation
│   ├── llm/            # LLM client, prompts, schemas, OpenAPI converter
│   ├── runner/         # HTTP execution, verification, reporting
│   ├── tests/          # Unit and integration tests
│   ├── web/            # FastAPI routers and static UI assets
│   ├── cli.py          # CLI entry point
│   ├── config.py       # Application configuration
│   └── main.py         # FastAPI application entry point
├── mock/               # Mock API and fixtures for manual testing
├── scripts/
│   └── start.bat       # One-click Windows startup script
├── .env.example        # Example environment variables
├── .gitignore
├── LICENSE
├── pyproject.toml      # Project metadata and tool configuration
├── README.md
└── requirements.txt
```

## Prerequisites

- Python 3.10 or later
- Windows (the provided start script is `.bat`)
- [LM Studio](https://lmstudio.ai/) running locally with a loaded model, Local Server enabled
- (Optional) Microsoft C++ Build Tools for dependencies with native extensions

## Installation

1. Clone the repository:

   ```bash
   git clone <repository-url>
   cd QA-Agent
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

4. Copy the example environment file and adjust as needed:

   ```bash
   copy .env.example .env
   ```

   > Note: LM Studio URL and model name can also be supplied per session directly in the web UI.

5. (Recommended) Run the quick start script:

   ```bash
   scripts\start.bat
   ```

## Usage

### Web UI

1. Open the browser at `http://127.0.0.1:8001`.
2. Fill in the LM Studio base URL and model name, then click **Test Connection**.
3. Fill in the target API base URL and authentication details.
4. Upload a test suite document, or click **Gunakan OpenAPI.json** to generate a test suite from an OpenAPI spec first.
5. Click **Jalankan Test**.
6. Watch the loading animation showing the currently running test case.
7. When finished, review the summary and per-case details. Failed cases include an LLM explanation.
8. Click **Unduh Laporan (.xlsx)** to save the report to a location of your choice.

#### Using a Remote LM Studio

If LM Studio is running on another computer in the same local network, use its IP address in the UI, for example:

```text
http://192.168.1.10:1234/v1
```

The web UI itself runs on `127.0.0.1` (localhost) by default, so only the user on the same computer can open it. Only the LLM connection may go over the local network.

### CLI

```bash
# Basic run
venv\Scripts\python.exe -m app.cli --suite path/to/suite.docx --base-url http://localhost:8000 --auth-type none

# With bearer token
venv\Scripts\python.exe -m app.cli --suite suite.md --base-url http://localhost:8000 --auth-type bearer --token TOKEN

# With basic auth
venv\Scripts\python.exe -m app.cli --suite suite.docx --base-url http://localhost:8000 --auth-type basic --username u --password p

# Custom output directory
venv\Scripts\python.exe -m app.cli --suite suite.docx --base-url http://localhost:8000 --output reports/run-1
```

The CLI writes a single `report.xlsx` file in the output directory.

### OpenAPI Conversion

1. Open `http://127.0.0.1:8001/openapi`.
2. Fill in LM Studio base URL and model name.
3. Upload an OpenAPI JSON or YAML file.
4. Click **Generate Test Suite**.
5. Download the generated `.docx` file.
6. Return to the main page and upload the `.docx` file to run the tests.

### Mock API

The `mock/` folder provides a FastAPI mock API and a matching test suite:

```bash
# Start the mock API
venv\Scripts\python.exe -m uvicorn mock.api:app --host 127.0.0.1 --port 9000

# Run the test suite via CLI
venv\Scripts\python.exe -m app.cli --suite mock/test_suite.docx --base-url http://127.0.0.1:9000 --auth-type none --output reports/mock
```

The mock API exposes 10 endpoints with 2 deliberate bugs:

- `GET /api/v1/users/1` returns `id` as a string instead of a number.
- `GET /api/v1/books/99` returns HTTP 200 instead of 404.

Expected result: 8 PASS, 2 FAIL.

To reset the mock API state without restarting the server:

```bash
curl -X POST http://127.0.0.1:9000/reset
```

## Development

Install development dependencies:

```bash
pip install -e ".[dev]"
```

Run lint and format checks:

```bash
venv\Scripts\python.exe -m ruff check app\ mock\ --output-format concise
venv\Scripts\python.exe -m ruff format --check app\ mock\
```

Apply formatting:

```bash
venv\Scripts\python.exe -m ruff format app\ mock\
```

## Testing

Run all deterministic tests (excludes live LLM-dependent tests):

```bash
venv\Scripts\python.exe -m pytest app\tests\ --ignore=app\tests\live.py -q
```

Run lint and compile check:

```bash
venv\Scripts\python.exe -m ruff check app\ mock\ --output-format concise
venv\Scripts\python.exe -m compileall -q app\ mock\
```

## Security

- Auth credentials are kept in memory only while the pipeline runs.
- Uploaded files are stored temporarily and deleted after the job finishes.
- API keys/tokens are never written to reports.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

**Project Status:** This project is intended as a local tool for technical users. It is not hardened for public internet exposure.
