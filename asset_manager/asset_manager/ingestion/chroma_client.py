"""Builds the shared ChromaDB client.

Two modes, auto-selected by which env vars are set:

- **Chroma Cloud** (chromadb.CloudClient), when CHROMA_API_KEY is set —
  Chroma's own managed hosting. Needed for deployments with no way to run
  a local server process and no persistent disk (e.g. Streamlit
  Community Cloud: `ValueError: Could not connect to a Chroma server` —
  there's nothing listening on localhost there, and no way to run one
  alongside the app). Also needs CHROMA_TENANT and CHROMA_DATABASE.
- **Local client-server mode** (chromadb.HttpClient), the default —
  connects to a `chroma run` server process you run yourself, per
  CHROMA_HOST/CHROMA_PORT (defaults localhost:8001). This is what local
  development and any self-hosted deployment use.

Client-server mode (either flavor) exists because multiple separate OS
processes touch the same Chroma data in this project — the Streamlit app,
the automation API, and ingestion triggered by n8n — and a Chroma
PersistentClient's direct local-file access isn't safe for concurrent
multi-process access. Observed live: an "Error finding id" internal error
from a Streamlit chat query that happened to run at the same moment
scheduled ingestion was writing to the same on-disk files.

Local mode, start the server with:
    chroma run --path knowledge_base/chroma_db --port 8001
(matching CHROMA_HOST/CHROMA_PORT below, or the defaults).
"""

import os

import chromadb


def get_chroma_client():
    if os.environ.get("CHROMA_API_KEY"):
        return chromadb.CloudClient(
            tenant=os.environ.get("CHROMA_TENANT"),
            database=os.environ.get("CHROMA_DATABASE"),
            api_key=os.environ["CHROMA_API_KEY"],
        )
    host = os.environ.get("CHROMA_HOST", "localhost")
    port = int(os.environ.get("CHROMA_PORT", "8001"))
    return chromadb.HttpClient(host=host, port=port)
