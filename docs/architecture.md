# Architecture

DevMind AI is organised as a Clean Architecture. The goal is simple: the rules
that describe *what a documentation assistant is* must not depend on Streamlit,
SQLite or Microsoft Foundry Local.

## The dependency rule

Source code dependencies point **inwards** only.

```
┌──────────────────────────────────────────────┐
│ presentation  (Streamlit UI)                 │
│  ┌────────────────────────────────────────┐  │
│  │ application  (use cases, ports, DTOs)  │  │
│  │  ┌──────────────────────────────────┐  │  │
│  │  │ domain  (entities, contracts)    │  │  │
│  │  └──────────────────────────────────┘  │  │
│  └────────────────────────────────────────┘  │
│ infrastructure  (SQLite, parsers, Foundry)   │
└──────────────────────────────────────────────┘
```

`infrastructure` sits on the outside: it *implements* the ports declared by
`application` and the repository contracts declared by `domain`. Nothing inside
imports it.

## Layers

### `devmind/core`

Cross-cutting concerns available to every layer:

- `config.py` - immutable, validated settings loaded from the environment.
- `logger.py` - one-time logging setup, console plus rotating file handler.
- `exceptions.py` - the `DevMindError` root exception.

`core` never imports another layer.

### `devmind/domain`

Enterprise rules, expressed with plain Python objects:

- `entities/` - objects with identity (document, chunk, answer).
- `value_objects/` - immutable concepts without identity.
- `repositories/` - abstract persistence contracts.

Depends on the standard library and `core` only.

### `devmind/application`

Application-specific rules:

- `use_cases/` - one class per business operation, orchestrating the domain.
- `interfaces/` - ports for everything the use cases need from the outside
  world (embedding provider, chat client, parsers).
- `dto/` - flat data structures crossing the boundary to the UI.

Depends on `domain` and `core`.

### `devmind/infrastructure`

Adapters implementing the abstractions above:

- `persistence/` - SQLite repositories.
- `parsers/` - PDF, DOCX, Markdown and plain-text readers.
- `embeddings/` - vector generation through Foundry Local.
- `llm/` - chat completion through Foundry Local.

### `devmind/presentation`

The delivery mechanism: Streamlit pages and components. It calls use cases and
renders DTOs; it contains no business logic.

## Configuration

All settings are read exactly once, in `devmind.core.config`, and exposed as
frozen dataclasses grouped by concern. No other module reads environment
variables. Values are validated at load time, so a misconfigured process fails
immediately and with a precise message instead of failing later in the pipeline.

Relative paths are resolved against the project root, which makes behaviour
independent of the working directory.

## Logging

`configure_logging()` is called once at start-up. It installs a rotating file
handler (UTF-8) and, optionally, a console handler on the root logger, then
raises the level of noisy third-party loggers. Modules obtain a logger with
`get_logger(__name__)` and never configure handlers themselves.

The call is idempotent, which matters under Streamlit: a script rerun must not
duplicate handlers or log records.
