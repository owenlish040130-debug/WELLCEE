"""标签体系加载与关键词索引"""
from pathlib import Path
import yaml
from functools import lru_cache
from app.config import settings


@lru_cache(maxsize=1)
def load_taxonomy() -> dict:
    """加载标签体系 YAML"""
    path = settings.data_dir / "tag-taxonomy.yaml"
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_keyword_index(taxonomy: dict) -> dict[str, dict]:
    """
    构建 关键词 → 标签信息 的索引。
    key: 关键词，value: {tag_id, label, category, roommate_relevance}
    """
    index = {}
    for cat_key, category in taxonomy["categories"].items():
        for tag_def in category["tags"]:
            for keyword in tag_def["keywords"]:
                index[keyword] = {
                    "tag_id": tag_def["id"],
                    "label": tag_def["label"],
                    "category": cat_key,
                    "roommate_relevance": tag_def.get("roommate_relevance", "low"),
                }
    return index


def get_required_dimensions(demand_types: list[str]) -> list[str]:
    """根据需求类型返回应覆盖的维度列表"""
    dims = ["personality", "hobby", "lifestyle"]

    has = lambda x: any(x in t for t in demand_types)
    if has("find_roommate"):
        dims.append("roommate_expectation")
    if has("rent") or has("find_roommate_searching"):
        dims.append("rental_preference")
    if has("list") or has("transfer"):
        dims.append("listing_feature")
    if has("transfer"):
        dims.append("transfer_reason")

    return dims


def get_taxonomy_for_frontend(taxonomy: dict) -> dict:
    """返回前端渲染所需的精简版标签体系（去掉 keywords）"""
    result = {"version": taxonomy["version"], "categories": {}}
    for cat_key, category in taxonomy["categories"].items():
        result["categories"][cat_key] = {
            "label": category["label"],
            "icon": category["icon"],
            "description": category["description"],
            "tags": [
                {
                    "id": t["id"],
                    "label": t["label"],
                    "roommate_relevance": t.get("roommate_relevance", "low"),
                }
                for t in category["tags"]
            ],
        }
    return result
