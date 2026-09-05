"""Builds the shared ChromaDB client.

Uses Chroma's client-server mode (chromadb.HttpClient against a `chroma
run` server process) rather than PersistentClient (direct local file
access). Multiple separate OS processes touch the same Chroma data in this
project — the Streamlit app, the automation API, and ingestion triggered
by n8n — and PersistentClient's local file-based mode isn't safe for
concurrent multi-process access. Observed live: an "Error finding id"
internal error from a Streamlit chat query that happened to run at the
same moment n8n's scheduled ingestion was writing to the same on-disk
files. A single `chroma run` server process arbitrates all reads/writes
safely; every part of the app is a client of that one server instead of
opening the files directly.

Start the server with:
    chroma run --path knowledge_base/chroma_db --port 8001
(matching CHROMA_HOST/CHROMA_PORT below, or the defaults).
"""

import os

import chromadb


def get_chroma_client():
    host = os.environ.get("CHROMA_HOST", "localhost")
    port = int(os.environ.get("CHROMA_PORT", "8001"))
    return chromadb.HttpClient(host=host, port=port)
