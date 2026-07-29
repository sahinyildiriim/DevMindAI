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

- `entities/` - `ParsedDocument`, the common result of every parser,
  and `DocumentChunk`, the unit of retrieval.
- `value_objects/` - `DocumentFormat`, `DocumentMetadata`, `ChunkId`,
  `Embedding`.
- `repositories/` - abstract persistence contracts, one per table
  family, implemented by the infrastructure layer.
- `exceptions.py` - document errors under `DocumentError`.

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
- `chunking/` - strategies that split documents for retrieval.
- `embeddings/` - vector generation through Foundry Local.
- `llm/` - chat completion through Foundry Local.

### `devmind/presentation`

The delivery mechanism: Streamlit pages and components. It calls use cases and
renders DTOs; it contains no business logic.

## Document parsing

Parsing is deliberately split across three layers:

- `domain` owns the vocabulary: `DocumentFormat` (the single source of
  truth for supported extensions), `DocumentMetadata` and the common
  result model `ParsedDocument`.
- `application` owns the contracts: `DocumentParser` and
  `DocumentParserRegistry`.
- `infrastructure` owns the adapters: one parser per format, plus the
  registry that resolves a file to its parser in constant time.

`FileDocumentParser` is a template method. It performs everything that
is identical for every format - validation, SHA-256 checksumming,
metadata assembly, whitespace normalisation, logging and translation of
third party exceptions into `DocumentParseError` - and leaves a single
`extract()` hook to the concrete parsers. Adding a format therefore
means adding one enum member and one small class, and touching nothing
else.

Size limits are enforced before any content is read, and the checksum is
streamed in blocks, so memory usage stays flat regardless of document
size.

## Chunking

Chunking follows the same three-layer split as parsing:

- `domain` owns `DocumentChunk` and its identity `ChunkId`.
- `application` owns the `TextChunker` port.
- `infrastructure` owns `SlidingWindowChunker`, the default strategy.

The chunker is an adapter rather than a domain service, because the
strategy is interchangeable: a future semantic chunker will need an
embedding model, and it belongs next to the one shipped today.

Chunks overlap by a configurable number of characters, so a sentence
straddling a cut point stays retrievable from both sides. Cut points are
pulled back to the closest structural boundary - paragraph, line,
sentence, then word - as long as it lies within a fifth of the chunk
size; otherwise the text is cut exactly at the limit, which keeps
pathological input (a single long token) bounded.

Two invariants make chunks trustworthy downstream:

- `document.content[chunk.start_offset:chunk.end_offset] == chunk.content`,
  which is what lets a later citation point at the exact passage. It is
  enforced by `DocumentChunk` itself, not only by the chunker.
- `ChunkId` is derived from the document checksum and the chunk index,
  so re-ingesting an unchanged document reproduces the same identifiers
  and the index can be replaced instead of duplicated.

## Persistence

The knowledge base is a single SQLite file. Four tables hold everything:

| Table        | Holds                                            |
| ------------ | ------------------------------------------------ |
| `metadata`   | Key/value state of the index, incl. schema version |
| `documents`  | One row per indexed file                          |
| `chunks`     | One row per chunk, referencing its document       |
| `embeddings` | At most one vector per chunk                      |

Two rules keep the data honest:

- **Nothing derived is stored.** File names, character counts and word
  counts are computed from what is stored, so a fact can never disagree
  with itself.
- **Deletion cascades.** Removing a document removes its chunks, and
  removing a chunk removes its embedding, through foreign keys rather
  than through application code. `PRAGMA foreign_keys` is set on every
  connection, since SQLite leaves it off by default.

A document is identified by its source path: re-indexing the same file
updates its row and keeps the row identity, while the checksum tells
whether the content actually changed. The integer primary key exists
only to keep foreign keys compact and never leaves the persistence
layer, so the domain stays free of database artifacts.

`SqliteDatabase` is the only module that imports `sqlite3`. It owns the
connection lifecycle, applies the pragmas, wraps statements in
transactions and translates every `sqlite3` failure into `StorageError`.
Connections are thread-local, because a `sqlite3` connection may not be
shared between threads and Streamlit serves each interaction from its
own thread; write-ahead logging keeps readers and the single writer out
of each other's way.

Embedding vectors are stored as little-endian 32-bit floats. Narrowing
from Python's doubles turns an out-of-range value into infinity rather
than failing, so the encoder checks its own result instead of trusting
it.

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
