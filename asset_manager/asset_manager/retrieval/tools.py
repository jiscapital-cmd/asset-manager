"""Builds a LangChain tool per source_type, wrapping ChromaStore.query()."""

from langchain_core.tools import tool

from asset_manager.ingestion.store import ChromaStore
from asset_manager.property_ids import resolve_property_id


def make_retrieval_tool(store: ChromaStore, source_type: str, known_property_ids: list[str] | None = None):
    @tool(
        name_or_callable=f"retrieve_{source_type}_documents",
        description=(
            f"Retrieve {source_type} documents for a property, grounded in real files. "
            "Args: query (what to search for), property_id (which property's documents "
            "to search)."
        ),
    )
    def retrieve(query: str, property_id: str) -> str:
        if known_property_ids:
            property_id = resolve_property_id(property_id, known_property_ids)
        results = store.query(query, source_type=source_type, property_id=property_id)
        if not results:
            return f"No relevant {source_type} documents found for property '{property_id}'."

        formatted = []
        for r in results:
            formatted.append(f"[{r['filename']}, p.{r['page_or_row']}]: {r['text']}")
        return "\n\n".join(formatted)

    return retrieve
