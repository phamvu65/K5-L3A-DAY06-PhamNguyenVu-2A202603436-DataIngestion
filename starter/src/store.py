"""Persist chunk vectors and perform exact cosine search with pgvector."""
import json
from typing import Any

import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .models import Chunk


class PgVectorStore:
    def __init__(self, database_url: str, dimensions: int) -> None:
        if not 1 <= dimensions <= 16000:
            raise ValueError("Invalid pgvector dimensions.")
        self.database_url = database_url
        self.dimensions = dimensions

    def create_schema(self) -> None:
        with psycopg.connect(self.database_url, connect_timeout=5) as connection:
            connection.execute("SELECT pg_advisory_xact_lock(hashtext('day6_chunks'), 0)")
            connection.execute(sql.SQL("""
                CREATE TABLE IF NOT EXISTS day6_chunks (
                    strategy text NOT NULL,
                    chunk_id text NOT NULL,
                    document_id text NOT NULL,
                    source text NOT NULL,
                    page integer NOT NULL,
                    text text NOT NULL,
                    metadata jsonb NOT NULL,
                    embedding vector({dimensions}) NOT NULL,
                    PRIMARY KEY (strategy, chunk_id)
                )
            """).format(dimensions=sql.Literal(self.dimensions)))

    def upsert(self, strategy: str, chunks: list[Chunk], vectors: list[list[float]]) -> None:
        """Replace a strategy's complete corpus snapshot in one transaction."""
        if len(chunks) != len(vectors):
            raise ValueError("Expected one vector per chunk.")
        rows = [
            (strategy, chunk.chunk_id, chunk.document_id, chunk.source, chunk.page,
             chunk.text, Jsonb(chunk.metadata), self._vector_literal(vector))
            for chunk, vector in zip(chunks, vectors, strict=True)
        ]
        with psycopg.connect(self.database_url, connect_timeout=5) as connection:
            connection.execute(
                "SELECT pg_advisory_xact_lock(hashtext('day6_chunks'), hashtext(%s))",
                (strategy,),
            )
            connection.execute("DELETE FROM day6_chunks WHERE strategy = %s", (strategy,))
            with connection.cursor() as cursor:
                cursor.executemany("""
                    INSERT INTO day6_chunks
                        (strategy, chunk_id, document_id, source, page, text, metadata, embedding)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s::vector)
                """, rows)

    def search(self, strategy: str, query_vector: list[float], top_k: int = 3,
               filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        if top_k <= 0:
            raise ValueError("top_k must be positive.")
        filters = filters or {}
        if filters.keys() - {"chapter"}:
            raise ValueError("Only the chapter metadata filter is supported.")
        with psycopg.connect(self.database_url, connect_timeout=5, row_factory=dict_row) as connection:
            return connection.execute("""
                SELECT chunk_id, document_id, source, page, text, metadata,
                       1 - (embedding <=> %s::vector) AS score
                FROM day6_chunks
                WHERE strategy = %s AND metadata @> %s::jsonb
                ORDER BY score DESC, chunk_id
                LIMIT %s
            """, (self._vector_literal(query_vector), strategy, Jsonb(filters), top_k)).fetchall()

    def _vector_literal(self, vector: list[float]) -> str:
        if len(vector) != self.dimensions or not any(vector):
            raise ValueError("Expected a nonzero vector with the configured dimensions.")
        return json.dumps(vector, allow_nan=False)
