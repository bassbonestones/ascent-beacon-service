import httpx
from typing import Any

from app.core.config import settings


class LLMClient:
    """Client for LLM API calls (OpenAI-compatible)."""
    
    def __init__(self) -> None:
        self.base_url = settings.llm_base_url
        self.api_key = settings.llm_api_key
        self.model = settings.llm_model
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=30.0,
        )
    
    async def chat_completion(
        self,
        messages: list[dict[str, Any]],
        temperature: float = 0.7,
        max_tokens: int | None = None,
        response_format: dict[str, Any] | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Call the chat completion endpoint."""
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        
        if max_tokens:
            payload["max_tokens"] = max_tokens
        
        if response_format:
            payload["response_format"] = response_format
        
        if tools:
            payload["tools"] = tools
        
        if tool_choice:
            payload["tool_choice"] = tool_choice
        
        response = await self.client.post("/chat/completions", json=payload)
        response.raise_for_status()
        result: dict[str, Any] = response.json()
        return result
    
    async def create_embedding(self, text: str, model: str = "text-embedding-3-large") -> list[float]:
        """Create an embedding for text."""
        payload = {
            "model": model,
            "input": text,
        }
        
        response = await self.client.post("/embeddings", json=payload)
        response.raise_for_status()
        data: dict[str, Any] = response.json()
        embedding: list[float] = data["data"][0]["embedding"]
        return embedding
    
    async def close(self) -> None:
        """Close the HTTP client."""
        await self.client.aclose()


# Global LLM client instance
llm_client = LLMClient()
