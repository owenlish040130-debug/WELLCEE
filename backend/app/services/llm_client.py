"""
LLM 客户端：统一接口调用 DeepSeek、Qwen、GLM 三个厂商。
"""
import json
import logging
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential
from app.config import settings

logger = logging.getLogger(__name__)


class LLMClient:
    """多厂商 LLM 调用客户端"""

    def __init__(self):
        self._client = httpx.AsyncClient(timeout=settings.llm_timeout)

    async def _call_api(
        self,
        messages: list[dict],
        model: str,
        api_key: str,
        base_url: str,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> str:
        """底层 HTTP 调用"""
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        response = await self._client.post(
            f"{base_url}/chat/completions",
            headers=headers,
            json=payload,
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]

    # ─── Qwen-Plus（追问+标签，主线）───

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=1, max=3))
    async def call_qwen_plus(self, system_prompt: str, user_message: str) -> str:
        return await self._call_api(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            model="qwen-plus",
            api_key=settings.qwen_api_key,
            base_url=settings.qwen_base_url,
        )

    # ─── DeepSeek-V3（简介生成，主线）───

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=1, max=3))
    async def call_deepseek_v3(self, system_prompt: str, user_message: str) -> str:
        return await self._call_api(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            model="deepseek-chat",  # DeepSeek-V3
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
        )

    # ─── GLM-4-Air（备选）───

    @retry(stop=stop_after_attempt(1), wait=wait_exponential(multiplier=1, min=1, max=2))
    async def call_glm_air(self, system_prompt: str, user_message: str) -> str:
        return await self._call_api(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            model="glm-4-air",
            api_key=settings.glm_api_key,
            base_url=settings.glm_base_url,
        )

    # ─── GLM-4-Flash（免费兜底）───

    @retry(stop=stop_after_attempt(1))
    async def call_glm_flash(self, system_prompt: str, user_message: str) -> str:
        return await self._call_api(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            model="glm-4-flash",
            api_key=settings.glm_api_key,
            base_url=settings.glm_base_url,
        )

    async def close(self):
        await self._client.aclose()


# 单例
llm_client = LLMClient()
