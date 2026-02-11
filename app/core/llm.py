import httpx

from app.core.config import settings


class LLMClient:
    """Client for LLM API calls (OpenAI-compatible)."""
    
    def __init__(self):
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
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int | None = None,
        response_format: dict | None = None,
        tools: list[dict] | None = None,
        tool_choice: str | dict | None = None,
    ) -> dict:
        """Call the chat completion endpoint."""
        payload = {
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
        return response.json()
    
    async def create_embedding(self, text: str, model: str = "text-embedding-3-large") -> list[float]:
        """Create an embedding for text."""
        payload = {
            "model": model,
            "input": text,
        }
        
        response = await self.client.post("/embeddings", json=payload)
        response.raise_for_status()
        data = response.json()
        return data["data"][0]["embedding"]
    
    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()


# Global LLM client instance
llm_client = LLMClient()
