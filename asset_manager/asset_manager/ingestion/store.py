"""Chroma-backed storage for embedded document chunks."""

from dataclasses import dataclass
from typing import Callable


@dataclass
class ChunkRecord:
    id: str
    text: str
    property_id: str
    source_type: str
    filename: str
    page_or_row: int
    file_hash: str
    ingested_at: str


class ChromaStore:
    def __init__(self, client, embed_fn: Callable[[list[str]], list[list[float]]], collection_name: str = "documents"):
        self._embed_fn = embed_fn
        self._collection = client.get_or_create_collection(collection_name)

    def upsert_chunks(self, records: list[ChunkRecord]) -> None:
        if not records:
            return
        embeddings = self._embed_fn([r.text for r in records])
        self._collection.upsert(
            ids=[r.id for r in records],
            documents=[r.text for r in records],
            embeddings=embeddings,
            metadatas=[
                {
                    "property_id": r.property_id,
                    "source_type": r.source_type,
                    "filename": r.filename,
                    "page_or_row": r.page_or_row,
                    "file_hash": r.file_hash,
                    "ingested_at": r.ingested_at,
                }
                for r in records
            ],
        )

    def delete_by_filename(self, property_id: str, filename: str) -> None:
        self._collection.delete(where={"$and": [{"property_id": property_id}, {"filename": filename}]})

    def query(self, query_text: str, source_type: str, property_id: str | None = None, n_results: int = 5) -> list[dict]:
        where_clauses = [{"source_type": source_type}]
        if property_id is not None:
            where_clauses.append({"property_id": property_id})
        where = where_clauses[0] if len(where_clauses) == 1 else {"$and": where_clauses}

        embedding = self._embed_fn([query_text])[0]
        result = self._collection.query(query_embeddings=[embedding], n_results=n_results, where=where)

        if not result["ids"] or not result["ids"][0]:
            return []

        metadatas = result["metadatas"][0]
        documents = result["documents"][0]
        return [
            {
                "text": documents[i],
                "filename": metadatas[i]["filename"],
                "page_or_row": metadatas[i]["page_or_row"],
                "property_id": metadatas[i]["property_id"],
                "source_type": metadatas[i]["source_type"],
            }
            for i in range(len(documents))
        ]

    def get_file_hash(self, property_id: str, filename: str) -> str | None:
        result = self._collection.get(
            where={"$and": [{"property_id": property_id}, {"filename": filename}]},
            limit=1,
        )
        if not result["ids"]:
            return None
        return result["metadatas"][0]["file_hash"]

    def list_known_filenames(self, property_id: str) -> set[str]:
        result = self._collection.get(where={"property_id": property_id})
        return {m["filename"] for m in result["metadatas"]}
