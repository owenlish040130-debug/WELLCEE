"""
AI 编排器：模型路由、降级链、JSON Schema 校验。
主线 → 备线 → 免费兜底，每步都做 JSON 格式校验。
"""
import json
import logging
from jsonschema import validate, ValidationError
from app.config import settings
from app.core.prompt_engine import render_prompt
from app.services.llm_client import llm_client

logger = logging.getLogger(__name__)

# JSON Schema：/analyze 响应校验
ANALYZE_SCHEMA = {
    "type": "object",
    "required": ["tags", "questions"],
    "properties": {
        "tags": {
            "type": "object",
            "properties": {
                "personality": {"type": "array"},
                "hobby": {"type": "array"},
                "lifestyle": {"type": "array"},
                "roommate_expectation": {"type": "array"},
                "rental_preference": {"type": "array"},
                "listing_feature": {"type": "array"},
                "transfer_reason": {"type": "array"},
            },
        },
        "questions": {
            "type": "array",
            "maxItems": 3,
            "items": {
                "type": "object",
                "required": ["id", "text", "options"],
                "properties": {
                    "id": {"type": "string", "minLength": 1},
                    "text": {"type": "string"},
                    "dimension": {"type": "string"},
                    "strategy": {"type": "string"},
                    "options": {
                        "type": "array",
                        "minItems": 2,
                        "items": {
                            "type": "object",
                            "required": ["label"],
                            "properties": {
                                "label": {"type": "string"},
                                "tag": {"type": ["string", "null"]},
                            },
                        },
                    },
                },
            },
        },
    },
}

BIO_SCHEMA = {
    "type": "object",
    "required": ["bio"],
    "properties": {"bio": {"type": "string", "minLength": 1}},
}


def _parse_json_response(raw: str) -> dict:
    """从 LLM 返回文本中提取 JSON"""
    raw = raw.strip()
    # 直接解析
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    # 提取 ```json ... ``` 块
    if "```json" in raw:
        start = raw.index("```json") + 7
        end = raw.index("```", start)
        return json.loads(raw[start:end].strip())
    if "```" in raw:
        start = raw.index("```") + 3
        end = raw.index("```", start)
        return json.loads(raw[start:end].strip())
    raise ValueError(f"无法从 LLM 响应中提取 JSON: {raw[:300]}...")


async def analyze_with_fallback(
    free_text: str,
    demand_types: list[str],
    draft_tags: dict,
    dimension_gaps: list[dict],
    question_history: list[dict],
) -> dict:
    """
    追问+标签分析。
    降级链：Qwen-Plus → GLM-4-Air → GLM-4-Flash
    """
    prompt = render_prompt("analyze", {
        "free_text": free_text,
        "demand_types": demand_types,
        "draft_tags": draft_tags,
        "dimension_gaps": dimension_gaps,
        "question_history": question_history,
    })
    system = "你是一个专业的用户画像分析助手。只输出 JSON，不要输出其他内容。"

    # 如果没配任何 API Key，返回空结果
    has_any_key = settings.qwen_api_key or settings.deepseek_api_key or settings.glm_api_key
    if not has_any_key:
        logger.warning("analyze: 未配置任何 LLM API Key，返回空结果")
        return {"tags": {c: [] for c in ["personality","hobby","lifestyle","roommate_expectation","rental_preference","listing_feature","transfer_reason"]}, "questions": []}

    # Try Qwen-Plus (primary)
    if settings.qwen_api_key:
        try:
            raw = await llm_client.call_qwen_plus(system, prompt)
            result = _parse_json_response(raw)
            validate(instance=result, schema=ANALYZE_SCHEMA)
            logger.info("analyze: Qwen-Plus ✓")
            return result
        except Exception as e:
            logger.warning(f"analyze: Qwen-Plus 失败 ({e}), 降级 DeepSeek-V3")

    # Try DeepSeek-V3（当没有 Qwen 或 Qwen 失败时）
    if settings.deepseek_api_key:
        try:
            raw = await llm_client.call_deepseek_v3(system, prompt)
            result = _parse_json_response(raw)
            validate(instance=result, schema=ANALYZE_SCHEMA)
            logger.info("analyze: DeepSeek-V3 ✓")
            return result
        except Exception as e:
            logger.warning(f"analyze: DeepSeek-V3 失败 ({e}), 降级 GLM-4-Air")

    # Try GLM-4-Air (secondary)
    if settings.glm_api_key:
        try:
            raw = await llm_client.call_glm_air(system, prompt)
            result = _parse_json_response(raw)
            validate(instance=result, schema=ANALYZE_SCHEMA)
            logger.info("analyze: GLM-4-Air ✓")
            return result
        except Exception as e:
            logger.warning(f"analyze: GLM-4-Air 失败 ({e}), 降级 GLM-4-Flash")

        # Try GLM-4-Flash (free, last resort)
        try:
            raw = await llm_client.call_glm_flash(system, prompt)
            result = _parse_json_response(raw)
            validate(instance=result, schema=ANALYZE_SCHEMA)
            logger.info("analyze: GLM-4-Flash ✓ (降级模式)")
            return result
        except Exception as e:
            logger.error(f"analyze: 所有模型均失败 ({e})")

    raise RuntimeError("AI 分析暂不可用，请稍后重试。请检查 API Key 配置。")


async def generate_bio_with_fallback(
    free_text: str,
    confirmed_tags: dict[str, list[str]],
    demand_types: list[str],
) -> dict:
    """
    简介生成。
    降级链：DeepSeek-V3 → Qwen-Plus → GLM-4-Air
    """
    prompt = render_prompt("bio", {
        "free_text": free_text,
        "confirmed_tags": confirmed_tags,
        "demand_types": demand_types,
    })
    system = "你是一个文字编辑。只输出 JSON，不要输出其他内容。"

    has_any_bio_key = settings.deepseek_api_key or settings.qwen_api_key or settings.glm_api_key
    if not has_any_bio_key:
        logger.warning("bio: 未配置任何 LLM API Key")
        return {"bio": free_text[:200] if free_text else "这个人还没写自我介绍"}

    # Try DeepSeek-V3 (primary)
    if settings.deepseek_api_key:
        try:
            raw = await llm_client.call_deepseek_v3(system, prompt)
            result = _parse_json_response(raw)
            validate(instance=result, schema=BIO_SCHEMA)
            logger.info("bio: DeepSeek-V3 ✓")
            return result
        except Exception as e:
            logger.warning(f"bio: DeepSeek-V3 失败 ({e}), 降级 Qwen-Plus")

    # Try Qwen-Plus (fallback)
    if settings.qwen_api_key:
        try:
            raw = await llm_client.call_qwen_plus(system, prompt)
            result = _parse_json_response(raw)
            validate(instance=result, schema=BIO_SCHEMA)
            logger.info("bio: Qwen-Plus ✓ (降级)")
            return result
        except Exception as e:
            logger.warning(f"bio: Qwen-Plus 失败 ({e}), 降级 GLM-4-Air")

    # Try GLM-4-Air (last resort)
    if settings.glm_api_key:
        try:
            raw = await llm_client.call_glm_air(system, prompt)
            result = _parse_json_response(raw)
            validate(instance=result, schema=BIO_SCHEMA)
            logger.info("bio: GLM-4-Air ✓ (降级模式)")
            return result
        except Exception as e:
            logger.error(f"bio: 所有模型均失败 ({e})")

    raise RuntimeError("简介生成暂不可用，请稍后重试。请检查 API Key 配置。")
