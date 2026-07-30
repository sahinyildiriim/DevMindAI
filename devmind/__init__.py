"""DevMind AI - Ask your documentation.

A fully local Retrieval-Augmented Generation application built on
Microsoft Foundry Local. The package follows Clean Architecture:

``core``
    Cross-cutting concerns (configuration, logging, base exceptions).
``domain``
    Enterprise rules: entities, value objects and repository contracts.
``application``
    Use cases orchestrating the domain, plus the ports they depend on.
``infrastructure``
    Adapters implementing the ports: SQLite, parsers, embeddings, LLM.
``presentation``
    Delivery mechanism: the Streamlit user interface.

Dependencies always point inwards: ``presentation`` and
``infrastructure`` depend on ``application`` and ``domain``, never the
other way around.
"""

__version__ = "1.0.0"
__all__ = ["__version__"]
