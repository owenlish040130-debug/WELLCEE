"""
规则引擎：关键词精确匹配、维度覆盖检测、标签后处理。
LLM 主导理解 + 规则辅助提效：规则只追求高精度不追求高召回，
漏掉的标签留给 LLM 补充。
"""
from app.core.taxonomy import get_required_dimensions


def extract_draft_tags(
    free_text: str, taxonomy: dict, keyword_index: dict
) -> dict[str, list[dict]]:
    """
    精确关键词匹配提取草稿标签。
    返回按 category 分组的 dict，每个标签带 source='rule'。
    """
    result: dict[str, list[dict]] = {cat: [] for cat in taxonomy["categories"]}

    for keyword, info in keyword_index.items():
        if keyword not in free_text:
            continue

        cat_key = info["category"]
        existing_ids = [t["tag_id"] for t in result.get(cat_key, [])]
        if info["tag_id"] in existing_ids:
            continue

        result[cat_key].append({
            "label": info["label"],
            "tag_id": info["tag_id"],
            "source": "rule",
            "confidence": 0.9,
            "roommate_relevance": info["roommate_relevance"],
        })

    return {k: v for k, v in result.items() if v}


# 维度关键词映射（粗粒度覆盖检测）
DIM_KEYWORD_MAP = {
    "cleaning_habit": ["干净", "整洁", "打扫", "清洁", "洁癖", "卫生", "脏"],
    "noise_tolerance": ["安静", "噪音", "吵", "隔音", "吵闹"],
    "social_frequency": ["朋友", "访客", "带人", "聚会", "社交", "约朋友"],
    "cooking_attitude": ["做饭", "下厨", "厨房", "煮饭", "烹饪"],
    "pet_attitude": ["宠物", "猫", "狗", "养猫", "养狗", "过敏"],
    "smoking_attitude": ["吸烟", "抽烟", "烟味", "不吸烟"],
    "schedule": ["作息", "早睡", "晚睡", "夜猫子", "熬夜"],
}


def detect_dimension_gaps(
    free_text: str,
    demand_types: list[str],
    taxonomy: dict,
    keyword_index: dict,
) -> list[dict]:
    """
    检测用户文本中缺失的关键维度。
    只对室友匹配相关维度做检测（找室友 / 找室友+找房场景）。
    """
    has_roommate = any("roommate" in t for t in demand_types)
    if not has_roommate:
        return []

    gaps = []
    for dim, keywords in DIM_KEYWORD_MAP.items():
        covered = any(kw in free_text for kw in keywords)
        if not covered:
            gaps.append({
                "dimension": dim,
                "reason": f"室友匹配场景下「{dim}」维度未检测到覆盖",
            })

    return gaps


def post_process_tags(
    tags: dict[str, list[dict]], taxonomy: dict
) -> dict[str, list[dict]]:
    """
    标签后处理：去重、排序、互斥冲突解决。
    互斥标签组取 confidence 高者保留。
    """
    rules = taxonomy.get("mutual_exclusion_rules", [])

    for rule_group in rules:
        group_ids = set(rule_group["group"])
        conflicting = []

        for cat_key in list(tags.keys()):
            for tag in tags[cat_key]:
                if tag.get("tag_id") in group_ids:
                    conflicting.append((cat_key, tag))

        if len(conflicting) > 1:
            conflicting.sort(key=lambda x: x[1].get("confidence", 0), reverse=True)
            winner_cat, winner = conflicting[0]
            for cat_key, tag in conflicting[1:]:
                tags[cat_key] = [t for t in tags[cat_key] if t != tag]

    # 每分类内按 confidence 降序
    for cat_key in tags:
        tags[cat_key].sort(key=lambda t: t.get("confidence", 0), reverse=True)

    return tags
