"""Create document and query embeddings with OpenAI."""
import json
import os
from pathlib import Path
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from dotenv import load_dotenv


MODEL_NAME = "text-embedding-3-small"
DIMENSIONS = 1536
BATCH_SIZE = 64


class Embedder(Protocol):
    model_name: str
    dimensions: int

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Return one vector per input text, in the same order."""
        ...

    def embed_query(self, question: str) -> list[float]:
        """Return a query vector compatible with the stored document vectors."""
        ...


class OpenAIEmbedder:
    """Use the same model and dimensions for document and query vectors."""

    def __init__(self) -> None:
        load_dotenv(Path(__file__).resolve().parents[1] / ".env")
        self._api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not self._api_key:
            raise RuntimeError("Set OPENAI_API_KEY in the environment or starter/.env.")
        self.model_name = MODEL_NAME
        self.dimensions = DIMENSIONS
        self.input_tokens = 0

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if any(not item.strip() for item in texts):
            raise ValueError("Embedding inputs must contain text.")

        vectors = []
        for start in range(0, len(texts), BATCH_SIZE):
            vectors.extend(self._embed_batch(texts[start:start + BATCH_SIZE]))
        return vectors

    def embed_query(self, question: str) -> list[float]:
        return self.embed_documents([question])[0]

    def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        request = Request(
            "https://api.openai.com/v1/embeddings",
            data=json.dumps({
                "model": self.model_name,
                "input": texts,
                "dimensions": self.dimensions,
                "encoding_format": "float",
            }).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=30) as response:
                payload = json.load(response)
        except HTTPError as exc:
            # The response body may include account details. Report the status only.
            raise RuntimeError(f"OpenAI embeddings returned HTTP {exc.code}.") from None
        except (URLError, TimeoutError) as exc:
            raise RuntimeError(f"Could not reach the OpenAI embeddings API: {exc}") from None

        rows = sorted(payload["data"], key=lambda row: row["index"])
        if [row["index"] for row in rows] != list(range(len(texts))):
            raise RuntimeError("OpenAI returned unexpected embedding indices.")
        vectors = [row["embedding"] for row in rows]
        if any(len(vector) != self.dimensions for vector in vectors):
            raise RuntimeError("OpenAI returned an unexpected embedding dimension.")
        self.input_tokens += payload["usage"]["prompt_tokens"]
        return vectors
