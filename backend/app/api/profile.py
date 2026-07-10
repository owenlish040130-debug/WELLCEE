"""
个人资料 API 端点
- POST /api/profile/ai/analyze  — 追问生成 + 标签提取
- POST /api/profile/ai/bio       — 个人简介生成
- GET  /api/profile/tags/taxonomy — 标签体系获取
- PUT  /api/profile/fields        — 保存最终资料
"""
from fastapi import APIRouter, HTTPException
from app.core.schemas import (
    AnalyzeRequest, AnalyzeResponse,
    BioRequest, BioResponse,
    SaveProfileRequest, SaveProfileResponse,
)
from app.core.taxonomy import (
    load_taxonomy, build_keyword_index, get_taxonomy_for_frontend,
)
from app.core.rule_engine import (
    extract_draft_tags, detect_dimension_gaps, post_process_tags,
)
from app.core.orchestrator import analyze_with_fallback, generate_bio_with_fallback
from app.services.db import save_or_update_profile

router = APIRouter(prefix="/api/profile", tags=["profile"])


@router.post("/ai/analyze", response_model=AnalyzeResponse)
async def analyze_profile(req: AnalyzeRequest):
    """
    追问生成 + 标签提取（单次 LLM 调用）。
    规则引擎先粗筛 → LLM 看全文补充修正 → 返回追问 + 标签。
    前端可携带 question_history 多次调用。
    """
    taxonomy = load_taxonomy()
    keyword_index = build_keyword_index(taxonomy)

    # 合并原文 + 追问历史答案一起做规则匹配
    combined = req.free_text
    for qh in req.question_history:
        combined += " " + qh.get("answer", "")

    draft_tags = extract_draft_tags(combined, taxonomy, keyword_index)
    gaps = detect_dimension_gaps(combined, req.demand_types, taxonomy, keyword_index)

    try:
        result = await analyze_with_fallback(
            free_text=req.free_text,
            demand_types=req.demand_types,
            draft_tags=draft_tags,
            dimension_gaps=gaps,
            question_history=req.question_history,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    result["tags"] = post_process_tags(result["tags"], taxonomy)
    return AnalyzeResponse(**result)


@router.post("/ai/bio", response_model=BioResponse)
async def generate_bio(req: BioRequest):
    """简介生成（单次 LLM 调用）"""
    try:
        result = await generate_bio_with_fallback(
            free_text=req.free_text,
            confirmed_tags=req.confirmed_tags,
            demand_types=req.demand_types,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    return BioResponse(**result)


@router.get("/tags/taxonomy")
async def get_taxonomy():
    """获取标签体系（前端渲染标签选择界面用）"""
    taxonomy = load_taxonomy()
    return get_taxonomy_for_frontend(taxonomy)


@router.put("/fields", response_model=SaveProfileResponse)
async def save_profile(req: SaveProfileRequest):
    """保存最终资料"""
    user_id = "u_demo_001"  # TODO: 从认证上下文获取

    await save_or_update_profile(
        user_id=user_id,
        basic_fields=req.basic_fields,
        tags=req.tags,
        bio=req.bio,
    )

    tag_count = sum(len(v) for v in req.tags.values())
    score = min(tag_count * 10, 100)

    return SaveProfileResponse(
        success=True,
        profile_id=user_id,
        tag_count=tag_count,
        completeness_score=score,
    )
