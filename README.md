# DevMind AI

> **Ask your documentation.**

DevMind AI is a fully local Retrieval-Augmented Generation (RAG) application for
technical documentation. It indexes your documents, runs every model on your own
machine through **Microsoft Foundry Local**, and answers **only** from the
indexed sources - no cloud calls, no data leaving your device.

## Why

Technical documentation is large, fragmented and hard to search. DevMind AI turns
a documentation set into a grounded question-answering assistant that always
cites the source it used, and explicitly says when the answer is not in the
corpus.

## First-release knowledge sources

- Microsoft Learn
- ASP.NET Core Documentation
- .NET Architecture Guides

## Supported documents

| Format     | Extensions          | Extracted metadata            |
| ---------- | ------------------- | ----------------------------- |
| PDF        | `.pdf`              | Title, author, page count     |
| Word       | `.docx`             | Title, author                 |
| Markdown   | `.md`, `.markdown`  | Front matter, first heading   |
| Plain text | `.txt`              | Title derived from first line |

Whatever the format, parsing yields the same `ParsedDocument`: normalised
plain text plus uniform metadata, including a SHA-256 checksum used to
detect duplicates and changes between ingestion runs.

## Highlights

- **100% local** - inference runs on Foundry Local; nothing is sent to a remote API.
- **Grounded answers** - responses are restricted to the indexed documentation.
- **Clean Architecture** - domain logic is independent of frameworks and storage.
- **Lean dependency set** - SQLite for storage, Streamlit for the UI.

## Tech stack

| Concern        | Technology                        |
| -------------- | --------------------------------- |
| Language       | Python 3.13                       |
| Inference      | Microsoft Foundry Local           |
| Storage        | SQLite                            |
| User interface | Streamlit                         |
| Parsing        | pypdf, python-docx, markdown      |

## Architecture

The project follows Clean Architecture. Dependencies point inwards only:

```
presentation ──▶ application ──▶ domain
                      ▲              ▲
infrastructure ───────┘──────────────┘
```

| Layer            | Package                  | Responsibility                                        |
| ---------------- | ------------------------ | ----------------------------------------------------- |
| Core             | `devmind/core`           | Configuration, logging, base exceptions                |
| Domain           | `devmind/domain`         | Entities, value objects, repository contracts          |
| Application      | `devmind/application`    | Use cases, DTOs, ports                                 |
| Infrastructure   | `devmind/infrastructure` | SQLite, parsers, embeddings, Foundry Local client      |
| Presentation     | `devmind/presentation`   | Streamlit user interface                               |

See [docs/architecture.md](docs/architecture.md) for the layer rules in detail.

## Project layout

```
.
├── devmind/
│   ├── core/                  # Config, logging, base exceptions
│   ├── domain/                # entities/, value_objects/, repositories/
│   ├── application/           # dto/, interfaces/, use_cases/
│   ├── infrastructure/        # persistence/, parsers/, embeddings/, llm/
│   └── presentation/          # ui/
├── data/
│   ├── documents/             # Source documents (git-ignored)
│   └── db/                    # SQLite database (git-ignored)
├── docs/
├── logs/                      # Rotating log files (git-ignored)
├── tests/
│   └── unit/
├── .env.example
├── requirements.txt
└── requirements-dev.txt
```

## Getting started

### Prerequisites

- Python 3.13 or newer
- [Microsoft Foundry Local](https://learn.microsoft.com/azure/ai-foundry/foundry-local/)
  installed and running

### Installation

```bash
python -m venv .venv
```

```bash
.venv\Scripts\activate
```

```bash
pip install -r requirements.txt
```

### Configuration

Copy the environment template and adjust it to your setup:

```bash
copy .env.example .env
```

Every setting has a safe default, so an empty `.env` is valid. Real environment
variables always take precedence over `.env` entries. Confirm the Foundry Local
endpoint with:

```bash
foundry service status
```

## Development

Install the development toolchain:

```bash
pip install -r requirements-dev.txt
```

Run the checks:

```bash
pytest
```

```bash
ruff check .
```

```bash
mypy devmind
```

## Roadmap

| Sprint | Scope                                              | Status      |
| ------ | -------------------------------------------------- | ----------- |
| 0      | Project skeleton, configuration, logging            | Done        |
| 1      | Document parsers and the common result model        | Done        |
| 2      | Chunking engine with configurable size and overlap  | Done        |
| 3      | SQLite persistence and repositories                 | Done        |
| 4      | Foundry Local embeddings and the indexing run        | Done        |
| 5      | Semantic search over the stored vectors             | Done        |
| 6      | Grounded answer generation                          | Planned     |
| 7      | Streamlit user interface                            | Planned     |

## License

Released under the [MIT License](LICENSE).
