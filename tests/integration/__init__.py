"""Integration tests: several real components exercised together.

Unlike ``tests/unit``, where each test targets one class and only the
SQLite gateway is real, these tests run the actual pipeline - parsing,
chunking, persistence, embedding and retrieval - against a real
temporary knowledge base, end to end. Only Microsoft Foundry Local is
replaced, with a deterministic fake standing in for both the embedding
and the chat model, since no CI environment can depend on a locally
running model service.
"""
