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
- `similarity.py` - `cosine_similarity`, the pure ranking function
  behind semantic search.
- `exceptions.py` - document errors under `DocumentError`, plus
  `StorageError` and `EmbeddingError`.

Depends on the standard library and `core` only.

### `devmind/application`

Application-specific rules:

- `use_cases/` - one class per business operation, orchestrating the domain:
  `EmbedChunksUseCase`, `SearchChunksUseCase`, `AnswerQueryUseCase`.
- `interfaces/` - ports for everything the use cases need from the outside
  world: `DocumentParser`, `TextChunker`, `EmbeddingProvider`, `ChatProvider`.
- `dto/` - flat data structures crossing the boundary to the UI:
  `EmbeddingRun`, `SearchResult`, `Prompt`, `GeneratedAnswer`.
- `prompt_builder.py` - `PromptBuilder`, composing the grounded prompt from
  a query and its retrieved chunks. A plain class rather than a port: unlike
  the adapters above it, it has no external dependency to swap out.

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

## Embedding

Foundry Local serves an OpenAI-compatible API on the loopback
interface, so `FoundryEmbeddingProvider` talks to it through the
`openai` client instead of a bespoke HTTP layer. The service lifecycle
stays with the user (`foundry service start`), which keeps the
application free of process management and free of a dependency that
only exists to provide it.

`EmbedChunksUseCase` is the first use case in the project, and it lives
in the application layer because it orchestrates several ports without
knowing any of them concretely: it reads chunks, calls the provider and
writes vectors.

The run is **resumable by construction**. Pending work is not tracked in
memory but derived from the knowledge base:

```sql
LEFT JOIN embeddings e ON e.chunk_id = c.chunk_id AND e.model = ?
WHERE e.chunk_id IS NULL
```

Three properties fall out of that single predicate:

- A batch that fails leaves everything already written in place, and a
  later run continues from there. Failing fast is therefore safe, and no
  partial-failure bookkeeping is needed.
- Re-running on an unchanged index is a no-op.
- Switching to another model marks every chunk pending again, so an
  index never mixes vectors from two models.

The last property only holds while providers stamp their own model name
on what they return, so the use case verifies it: a provider that
announced one model and returned another would otherwise loop forever.

Batching happens twice, for two different reasons. The use case reads,
embeds and writes `batch_size` chunks per step so that memory stays flat
and progress is durable; the provider splits whatever it is given into
requests of the same size, so that a direct caller cannot overwhelm the
service. In the normal path the two coincide and each step is one
request.

## Semantic search

`SearchChunksUseCase` ranks stored chunks against a query. There is no
vector index library: `EmbeddingRepository.list_all(model)` reads every
stored vector from the provider's own model, `cosine_similarity`
(`devmind/domain/similarity.py`) scores each one against the query
vector in plain Python, and `heapq.nlargest` picks the top matches. At
the scale of a single curated documentation set this brute-force scan
is fast enough, and it avoids a dependency whose only job would be to
approximate a computation that is already exact and quick without it.

Filtering by `min_score` happens *before* selecting the top matches, not
after: taking the global top-K first and filtering second could throw
away a result that would have qualified once a weaker one ahead of it
was excluded. Filter-then-select always returns the best *qualifying*
matches, up to the limit.

`cosine_similarity` doubles as the confidence score exposed on
`SearchResult`. Cosine similarity is mathematically defined on
[-1, 1]; the function clamps it to [0, 1] so the value is always usable
as a confidence measure - a negative direction carries no relevance
signal and is treated the same as no similarity at all, and the upper
bound absorbs floating point drift when a vector is compared to itself.

Filtering by model means comparing against an index built with a
different model naturally yields no results rather than a nonsensical
score or a dimension-mismatch crash: `list_all` never mixes vectors
from two models in the first place.

## Grounded answer generation

`AnswerQueryUseCase` is the last step of the pipeline: it turns a
`SearchChunksUseCase` result into an answer, through the same
Foundry-Local-via-`openai`-client pattern used for embeddings
(`FoundryChatProvider`, `infrastructure/llm`).

Hallucination prevention is layered, because a prompt alone cannot
*guarantee* a model's behaviour:

1. **Retrieval as a hard gate.** When `SearchChunksUseCase` finds no
   context at all, `AnswerQueryUseCase` returns the fixed sentence
   directly and never calls the chat model. This is the strong
   guarantee: it does not depend on the model choosing to cooperate.
2. **The system prompt as a soft gate.** `PromptBuilder`
   (`application/prompt_builder.py`) instructs the model to answer only
   from the numbered excerpts it is given and to reply with that exact
   same sentence if the excerpts turn out not to answer the question.
   This covers the case retrieval cannot detect on its own: chunks that
   cleared the similarity threshold but do not actually contain the
   answer.

The two paths share one constant, `NO_CONTEXT_ANSWER`, so the wording
can never drift between what code returns and what the model is told
to say.

Citations are attached by `AnswerQueryUseCase`, never asked of the
model: `GeneratedAnswer.citations` is exactly the `SearchResult` tuple
retrieval produced. Sourcing attribution from what was actually
retrieved - rather than parsing it out of the model's prose - removes
an entire class of hallucinated or malformed citations by construction.

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
