# Installation

This guide covers a full local setup: Microsoft Foundry Local, the Python
environment, configuration and verification. For the short version, see the
[README](../README.md#getting-started).

## 1. Prerequisites

| Requirement | Notes |
| --- | --- |
| Windows, macOS or Linux | Foundry Local supports all three; commands below show Windows (PowerShell) with a Unix equivalent alongside. |
| Python 3.13 or newer | Check with `python --version`. |
| ~5 GB free disk space | For the virtual environment, the local models and the SQLite knowledge base. |

DevMind AI itself has no GPU requirement; whether inference runs on GPU or
CPU is entirely up to how Foundry Local is configured on your machine.

## 2. Install Microsoft Foundry Local

Foundry Local is the on-device inference runtime DevMind AI talks to. It is
not a Python package and is installed separately.

1. Follow the official installer for your OS: [Microsoft Foundry Local
   documentation](https://learn.microsoft.com/azure/ai-foundry/foundry-local/).
2. Start the service:

   ```bash
   foundry service start
   ```

3. Pull the two models DevMind AI expects by default (both are small enough
   to run comfortably on a laptop):

   ```bash
   foundry model run phi-3.5-mini
   foundry model run all-minilm-l6-v2
   ```

   Running a model the first time downloads it; subsequent starts are fast.
   Different model names can be used instead - see
   [Configuration](#5-configure-devmind-ai) below - as long as both a chat
   and an embedding model are available.

4. Confirm the service is up and note the endpoint it prints:

   ```bash
   foundry service status
   ```

   By default this is `http://localhost:5273/v1`, already the default in
   `.env.example`. If your installation reports a different port, you will
   set it in step 5.

## 3. Get the source

```bash
git clone https://github.com/sahinyildiriim/DevMindAI.git
cd DevMindAI
```

(If you already have the source, skip this step.)

## 4. Create a Python environment

```bash
python -m venv .venv
```

Activate it:

```bash
# Windows (PowerShell)
.venv\Scripts\activate
```

```bash
# macOS / Linux
source .venv/bin/activate
```

Install the runtime dependencies:

```bash
pip install -r requirements.txt
```

Installing the development toolchain (`pytest`, `ruff`, `mypy`) as well is
only needed if you intend to run the test suite or modify the code:

```bash
pip install -r requirements-dev.txt
```

## 5. Configure DevMind AI

Copy the environment template:

```bash
# Windows
copy .env.example .env
```

```bash
# macOS / Linux
cp .env.example .env
```

Every setting has a working default, so an unedited `.env` is valid as long
as Foundry Local is reachable at `http://localhost:5273/v1` with the two
default models pulled. Open `.env` if you need to change any of the
following:

| Variable | When to change it |
| --- | --- |
| `DEVMIND_FOUNDRY_ENDPOINT` | Foundry Local reported a different port in step 2.4. |
| `DEVMIND_FOUNDRY_CHAT_MODEL` / `DEVMIND_FOUNDRY_EMBEDDING_MODEL` | You pulled different model names. |
| `DEVMIND_DOCUMENTS_DIR` / `DEVMIND_DB_PATH` | You want documents or the knowledge base stored somewhere other than `data/`. |
| `DEVMIND_CHUNK_SIZE`, `DEVMIND_TOP_K`, `DEVMIND_MIN_SCORE` | You want to tune retrieval; see [Configuration](architecture.md#configuration) for what each does. |

Real environment variables always take precedence over `.env`, which makes
container and CI overrides predictable.

## 6. Verify the setup

Run the test suite - it exercises the whole pipeline against a temporary
knowledge base and does not touch Foundry Local, so it passes independently
of whether the service is running:

```bash
pytest
```

Then launch the application:

```bash
streamlit run app.py
```

Open the URL Streamlit prints (typically `http://localhost:8501`). The
**Settings** page shows the configuration actually in effect, which is the
fastest way to confirm the endpoint and model names are what you expect.

## Troubleshooting

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| A page shows "Cannot reach the ... model at '...'. Make sure Foundry Local is running" | The service is not running, or is on a different port than configured. | `foundry service start`, then `foundry service status`; update `DEVMIND_FOUNDRY_ENDPOINT` if the port differs. |
| Uploading a document fails immediately | Its extension is not one of `.pdf`, `.docx`, `.md`, `.markdown`, `.txt`, or the file exceeds `DEVMIND_MAX_FILE_SIZE_MB`. | Convert the file, or raise the limit in `.env`. |
| Knowledge Base page shows a stale-model warning | The embedding model was changed after documents were already embedded. | Re-run indexing (Upload Documents page's embedding step re-embeds everything pending under the new model). |
| `streamlit run app.py` starts but the browser tab is blank | The port Streamlit chose is already in use by another process. | Stop the other process, or run with `streamlit run app.py --server.port 8502`. |
