# Changelog

All notable changes to DevMind AI are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and version numbers follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- Embedding now reports its progress live: a progress bar plus the
  number of chunks embedded so far and the document currently being
  processed, shown both while uploading new documents and when using
  the Embed pending chunks button. Previously a long first embedding
  run gave no feedback until it finished, which could make the
  application look frozen.

### Fixed

- The Knowledge Base page now shows an **Embed pending chunks** button
  whenever chunks are awaiting embedding. Previously, embedding only ran
  automatically right after uploading new or changed files; if that run
  never happened - for instance because Foundry Local was not yet
  running - there was no way to trigger it afterwards, since re-uploading
  an unchanged file is always skipped and a skipped file never triggers
  embedding.

## [1.0.0] - 2026-07-30

First release. DevMind AI indexes a local documentation set and answers
questions from it, entirely on-device through Microsoft Foundry Local.

### Added

**Document ingestion**
- Parsers for PDF, DOCX, Markdown and plain text, unified behind a single
  `ParsedDocument` result carrying normalised text and metadata (title,
  author, page count where the format provides it, plus a SHA-256
  checksum used to detect unchanged and updated files).
- A sliding-window chunking engine with configurable size and overlap,
  cutting at paragraph, sentence or word boundaries where possible.
- `IndexDocumentUseCase`, skipping re-chunking and re-storage entirely
  when a re-indexed file's content has not changed.

**Storage**
- A local SQLite knowledge base (documents, chunks, embeddings and
  index-level metadata), with cascading deletes, write-ahead logging and
  a schema version check at start-up.

**Embedding and retrieval**
- `FoundryEmbeddingProvider`, batching requests to Foundry Local's
  OpenAI-compatible embeddings endpoint.
- A resumable embedding run: pending work is derived from the knowledge
  base itself, so an interrupted run picks up where it left off, and
  switching embedding models re-embeds everything under the new one
  without mixing vectors from two models.
- Brute-force cosine similarity search with confidence scoring, ranking
  and thresholding, and no vector index dependency.

**Grounded answer generation**
- `FoundryChatProvider`, generating answers through Foundry Local's chat
  completion endpoint.
- Two-layer hallucination prevention: retrieval finding nothing is a hard
  gate that returns a fixed refusal without ever calling the model; a
  system prompt is a second gate for chunks that matched but do not
  answer the question.
- Source citations attached from what retrieval actually returned, never
  parsed from the model's own reply.

**Chat Service and Knowledge Base Service**
- Two composition roots wiring the pipeline above into the calls a
  delivery mechanism needs: asking a question, and indexing, embedding
  and inspecting the knowledge base.

**Streamlit user interface**
- Four pages: **Chat** (ask a question, see the answer, its confidence
  and its sources), **Upload Documents** (add files, with automatic
  embedding of anything new), **Knowledge Base** (document and chunk
  counts, embedding model status) and **Settings** (read-only
  configuration).

**Quality**
- 344 automated tests: unit tests against a real temporary SQLite file
  for every persistence-touching component, and integration tests
  driving the real composition roots end to end (index, embed, search,
  answer) against one real knowledge base.
- `ruff` and `mypy --strict` enforced across the codebase.

[Unreleased]: https://github.com/sahinyildiriim/DevMindAI/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/sahinyildiriim/DevMindAI/releases/tag/v1.0.0
