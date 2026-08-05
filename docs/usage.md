# Usage

A walkthrough of DevMind AI's four pages, in the order you would normally
use them. See [Installation](installation.md) if the application is not
running yet.

## 1. Upload Documents

Open the **Upload Documents** page and choose one or more files
(`.pdf`, `.docx`, `.md`, `.markdown` or `.txt`). For a first try, the
project's own [`README.md`](../README.md) or
[`docs/architecture.md`](architecture.md) work well.

Click **Index documents**. Each file is reported as it is processed:

```
✅ aspnet-core-routing.pdf: 12 chunk(s)
🔄 dependency-injection.md: unchanged, skipped
✅ clean-architecture.md: 4 chunk(s)
```

- **✅** - the file was new or had changed since the last upload, and was
  chunked and stored.
- **🔄** - an identical version of the file was already indexed; nothing
  was re-chunked or re-embedded. Re-uploading the same file is always
  safe.
- The embedding step runs once after every file in the batch, not once per
  file, so uploading several documents together is more efficient than
  uploading them one at a time.

If anything needs embedding, a progress bar tracks that step so a large
first upload never looks frozen:

```
Embedding documents... 52%
██████████░░░░░░░░░
Processed: 624 / 1200 chunks
Current document: ASP.NET-Core.pdf
```

Once it finishes, the final count replaces the progress bar:

```
Embedded 1200 chunk(s) in 3 batch(es).
```

A file that fails - an unsupported format, or one larger than the
configured limit - is reported inline without affecting the others:

```
❌ scanned-report.pdf: No extractable text found in 'scanned-report.pdf'.
   The document is empty or contains images only.
```

## 2. Knowledge Base

The **Knowledge Base** page answers three questions at a glance:

- **How much is indexed?** - document and chunk counts.
- **Is everything embedded?** - an *Embedded* count of `chunks with a
  vector / total chunks`, and, underneath, one of three states:
  - *"Model configured: ..., nothing embedded yet"* - a fresh knowledge
    base, before the first embedding run.
  - *"Embeddings are up to date with ..."* - every chunk has a vector from
    the currently configured model.
  - *"Stored embeddings were produced with X, but Y is now configured"* -
    the embedding model was changed after documents were indexed; re-run
    indexing on the Upload Documents page to bring it up to date.

  Whenever chunks are awaiting embedding, an **Embed pending chunks**
  button appears underneath. This is the button to use if embedding did
  not run automatically the first time - for instance because Foundry
  Local was not running yet when documents were uploaded. Re-uploading
  the same files again would not help in that case: an unchanged file
  is skipped, and skipped files never trigger embedding, so if the
  embedding step failed the first time, this button is what actually
  finishes the job. It shows the same progress bar described above
  while it runs.
- **What is indexed?** - a table of every document, its format, size and
  last modification time.

## 3. Chat

Type a question in the box at the bottom of the **Chat** page. DevMind AI
embeds the question, searches the knowledge base and, if it finds relevant
content, asks the local chat model to answer *using only that content*.

**A grounded answer** looks like this:

> **You:** How does endpoint routing work in ASP.NET Core?
>
> **DevMind AI:** Endpoint routing matches an incoming request to an
> endpoint based on its path. Routing middleware examines the request and
> dispatches it to the endpoint registered for that route.
>
> ▸ **Sources (2)**
> &nbsp;&nbsp;**ASP.NET Core Routing** — confidence: 87%
> &nbsp;&nbsp;**Middleware Pipeline** — confidence: 64%

Expand **Sources** to see which document each part of the answer came from
and how confident the match was (0-100%, based on how closely the source
text matches the question). Citations are always the chunks actually
retrieved for that question, never a list the model invented.

**When nothing relevant is indexed**, DevMind AI does not guess:

> **You:** What is the capital of France?
>
> **DevMind AI:** I couldn't find enough information in the indexed
> documents.

This is deliberate: an empty knowledge base, or a question far outside
what has been indexed, always produces this exact sentence rather than an
answer from the model's own general knowledge - the reason DevMind AI can
say every answer it gives is grounded in your documentation.

If Foundry Local itself is unreachable, the answer area shows that
directly (e.g. *"Cannot reach the chat model at '...'. Make sure Foundry
Local is running..."*) instead of a generated answer.

## 4. Settings

Read-only view of the active configuration: which chat and embedding
models are configured, the Foundry Local endpoint, retrieval parameters
(top-K, minimum confidence, chunk size) and where the knowledge base and
document files live on disk. Useful for confirming what is actually in
effect - see [Configuration](architecture.md#configuration) for what each
value controls, and [Installation](installation.md#5-configure-devmind-ai)
for how to change one.
