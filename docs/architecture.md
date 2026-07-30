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
  `StorageError`, `EmbeddingError` and `GenerationError`.

Depends on the standard library and `core` only.

### `devmind/application`

Application-specific rules:

- `use_cases/` - one class per business operation, orchestrating the domain:
  `IndexDocumentUseCase`, `EmbedChunksUseCase`, `GetKnowledgeBaseStatsUseCase`,
  `SearchChunksUseCase`, `AnswerQueryUseCase`.
- `interfaces/` - ports for everything the use cases need from the outside
  world: `DocumentParser`, `TextChunker`, `EmbeddingProvider`, `ChatProvider`.
- `dto/` - flat data structures crossing the boundary to the UI:
  `IndexingResult`, `KnowledgeBaseStats`, `EmbeddingRun`, `SearchResult`,
  `Prompt`, `GeneratedAnswer`.
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
- `chat_service.py` - `ChatService` and `build_chat_service`, the composition
  root wiring the pieces above into the one call a delivery mechanism needs
  to ask a question. See "Chat Service" below.
- `knowledge_base_service.py` - `KnowledgeBaseService` and
  `build_knowledge_base_service`, the composition root for indexing documents
  and reading the knowledge base's counts and embedding status. See
  "Knowledge Base Service" below.

### `devmind/presentation`

The delivery mechanism: a Streamlit application. It calls use cases (through
the two composition roots above) and renders DTOs; it contains no business
logic of its own.

- `ui/app.py` - `run()`, assembling the four pages into `st.navigation`.
  `app.py` at the project root is the thin script Streamlit actually executes
  (`streamlit run app.py`); it only calls this function.
- `ui/services.py` - `get_chat_service()` / `get_knowledge_base_service()`,
  wrapping the infrastructure factories in `st.cache_resource` so each is
  built once per server process rather than on every rerun.
- `ui/pages/` - one module per page (`chat`, `upload_documents`,
  `knowledge_base`, `settings`), each exposing a single `render()` function.

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

## Chat Service

`AnswerQueryUseCase` already performs every step a chat interaction
needs - take the question, call retrieval, build the prompt, call the
model, return the answer and its citations - as plain, testable
application logic with no concrete dependency on SQLite or Foundry
Local. What it does not do, by design, is assemble itself: building one
requires a `SqliteDatabase`, two repositories, an embedding provider and
a chat provider, each configured from settings.

`ChatService` (`infrastructure/chat_service.py`) is that assembly. It is
a composition root, not a second use case: `ChatService.ask()` is a
single delegation to `AnswerQueryUseCase.execute()`, plus one thing a
pure use case deliberately leaves out - logging which sources, by
title and confidence, the answer was grounded in, since that is exactly
what a delivery mechanism (a UI, a CLI, an operator watching logs)
wants to see and nothing a domain-level use case should need to care
about. `build_chat_service()` reads `Settings` once and wires
everything behind it; the returned service owns the knowledge base
connection and must be closed with `ChatService.close()` once it is no
longer needed.

Placing a class that imports from every layer inside `infrastructure`
looks, at first glance, like it breaks the dependency rule. It does
not: the dependency rule constrains the *direction* dependencies point
in ordinary business logic, and a composition root's entire job is to
sit at the outermost ring and wire the layers beneath it together - the
alternative would be scattering that wiring across every future caller
instead of writing it once.

## Knowledge Base Service

Uploading a document needs a step nothing before it provided: parsing,
chunking and storing a file is one operation, and no use case performed
it end to end. `IndexDocumentUseCase` (`application/use_cases`) is that
operation. Re-indexing a document whose checksum has not changed skips
chunking and storage entirely - `ChunkId` is derived from the checksum,
so redoing the work would only reproduce the rows already there.
Embedding stays a separate step, run once over the whole knowledge base
by `EmbedChunksUseCase` after any number of documents have been indexed,
rather than once per file.

`GetKnowledgeBaseStatsUseCase` reads the counts and embedding status the
Knowledge Base page shows. Its one piece of logic - deciding whether the
stored embeddings match the currently configured model - reads
`pending_embedding_count` from `ChunkRepository.count_pending_embedding`,
the same predicate `EmbedChunksUseCase` itself uses to find pending
work, rather than approximating it from a separate, looser count. When
nothing has been embedded yet, the model is reported as current: there
is no stale model to warn about, only work still to be done.

`KnowledgeBaseService` (`infrastructure/knowledge_base_service.py`) is
the composition root for these two use cases plus `EmbedChunksUseCase`,
mirroring `ChatService`. It opens its own `SqliteDatabase` rather than
sharing `ChatService`'s: two independent connections to the same
WAL-mode file coexist safely, which is simpler than giving two
unrelated services shared ownership of one connection's lifecycle.

## Streamlit UI

`app.py` at the project root is what `streamlit run app.py` executes; it
immediately hands off to `devmind.presentation.ui.app.run()`, which
configures the page and builds `st.navigation` from four pages, each a
module under `ui/pages/` exposing a single `render()` function: **Chat**,
**Upload Documents**, **Knowledge Base** and **Settings**.

Every page reaches the rest of the application through exactly two
calls, `get_chat_service()` and `get_knowledge_base_service()`
(`ui/services.py`). Streamlit reruns the whole script on every
interaction, so both are wrapped in `st.cache_resource`: the underlying
`ChatService` / `KnowledgeBaseService` - and the SQLite connection and
Foundry Local clients each owns - are built once per server process and
reused, never reopened on a keystroke. In this deployment neither
service's `close()` is ever called during normal operation: a
cache-resource-held object lives for the server's lifetime, and the
operating system reclaims the SQLite handle when the process exits,
same as any other long-lived server would.

Pages stay thin by design. Each does three things and nothing else:
collect input, call one of the two services, and render the DTO that
comes back. The one piece of local state is the Chat page's turn
history in `st.session_state` - purely a transcript of what was shown,
not conversational memory fed back into retrieval, since
`AnswerQueryUseCase` answers each question independently. Every call
into a service is wrapped in `except (DevMindError, ValueError)`: the
exceptions raised from Sprint 4 onward already carry actionable text
(an unreachable Foundry Local error includes the `foundry service start`
hint), so the UI's error handling is rendering that text with `st.error`,
not writing new messages.

Uploaded files are saved by name only - `Path(uploaded_file.name).name`
strips any directory component the browser might send - into the
configured documents directory, so an upload can never write outside
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
