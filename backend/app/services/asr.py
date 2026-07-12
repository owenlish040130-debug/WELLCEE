"""
阿里云 DashScope Paraformer-v2 语音识别服务。
免费额度 36,000 次，16kHz WAV 输入。
"""
import logging
import httpx
from app.config import settings

logger = logging.getLogger(__name__)

DASHSCOPE_ASR_URL = "https://dashscope.aliyuncs.com/api/v1/services/audio/asr/transcription"


async def transcribe_audio(audio_bytes: bytes, sample_rate: int = 16000) -> str:
    """
    调用 Paraformer-v2 将音频转为文本。

    Args:
        audio_bytes: WAV/PCM 音频数据
        sample_rate: 采样率，默认 16000

    Returns:
        识别出的中文文本
    """
    if not settings.dashscope_api_key:
        raise RuntimeError("未配置 DASHSCOPE_API_KEY")

    headers = {
        "Authorization": f"Bearer {settings.dashscope_api_key}",
        "Content-Type": "application/octet-stream",
        "X-DashScope-SampleRate": str(sample_rate),
        "X-DashScope-Format": "webm",
    }

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            DASHSCOPE_ASR_URL,
            headers=headers,
            content=audio_bytes,
        )
        response.raise_for_status()
        data = response.json()

    # DashScope 返回格式: {"output": {"sentence": {"text": "识别结果"}}}
    text = data.get("output", {}).get("sentence", {}).get("text", "")
    if not text:
        logger.warning(f"ASR 返回空文本，完整响应: {data}")

    return text
