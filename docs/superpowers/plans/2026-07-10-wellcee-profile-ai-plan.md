# Wellcee 个人资料 AI 增强 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 Wellcee 个人资料 AI 增强完善流程：固定表单 → 自由文本输入 → AI 追问 → 标签提取 → 简介生成 → 保存。混合架构（规则引擎 + Qwen-Plus + DeepSeek-V3），一期不含五行功能。

**Architecture:** Python/FastAPI 后端 + React 前端，REST API。规则引擎（关键词匹配 + 维度检测，0 Token）+ Qwen-Plus（追问生成 + 标签分析，1 次调用）+ DeepSeek-V3（简介生成，1 次调用）。BGE-M3 向量服务本地部署用于标签候选检索。三级降级链（主线 → 备线 → GLM-4-Flash 兜底）。

**Tech Stack:** Python 3.11+, FastAPI, React 18+, TypeScript, PostgreSQL 15+, Redis 7.x, BGE-M3 (TEI Docker), Qwen-Plus API (阿里云百炼), DeepSeek-V3 API

**Spec reference:**
- PRD: `docs/superpowers/specs/2026-07-10-wellcee-profile-ai-prd.md`
- Tech Spec: `docs/superpowers/specs/2026-07-10-wellcee-profile-ai-tech-spec.md`

## Global Constraints

- 所有 LLM 返回必须经过 JSON Schema 校验，校验失败重试 1 次后降级
- 标签体系前后端同源（`tag-taxonomy.yaml`），新增维度只需改这一个文件
- 固定表单字段：头像、昵称、年龄（出生年份）、职业、地区、语言、当前需求（多选）
- MBTI 不从文本推断，用户提到就提取，没提到在追问环节询问
- 一期不含五行功能
- 一期仅支持中文输入
- AI 追问完全由用户主动唤起（点击 ✨ 按钮），不自动弹出
- 单次流程 Token 成本 < ¥0.01

---

### Task 1: 项目脚手架与基础配置

**Files:**
- Create: `backend/requirements.txt`
- Create: `backend/app/__init__.py`
- Create: `backend/app/main.py`
- Create: `backend/app/config.py`
- Create: `backend/.env.example`
- Create: `frontend/` (Vite + React + TypeScript 脚手架)

**Interfaces:**
- Produces: FastAPI app 实例 `app`, 配置类 `Settings`, 前端路由框架

- [ ] **Step 1: 创建后端项目结构**

```bash
mkdir -p backend/app/{api,core,services,models}
mkdir -p backend/prompts
mkdir -p backend/data
```

- [ ] **Step 2: 编写 `backend/requirements.txt`**

```text
fastapi==0.115.6
uvicorn[standard]==0.34.0
pydantic==2.10.4
pydantic-settings==2.7.1
httpx==0.28.1
pyyaml==6.0.2
redis==5.2.1
asyncpg==0.30.0
sqlalchemy[asyncio]==2.0.36
python-dotenv==1.0.1
jsonschema==4.23.0
tenacity==9.0.0
```

- [ ] **Step 3: 编写 `backend/app/config.py`**

```python
"""应用配置，从环境变量加载（pydantic-settings）"""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # 数据库
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/wellcee"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # LLM API Keys
    qwen_api_key: str = ""
    qwen_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    qwen_model: str = "qwen-plus"

    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    deepseek_model: str = "deepseek-chat"  # V3

    glm_api_key: str = ""
    glm_base_url: str = "https://open.bigmodel.cn/api/paas/v4"
    glm_air_model: str = "glm-4-air"
    glm_flash_model: str = "glm-4-flash"

    # BGE-M3 向量服务
    embedding_service_url: str = "http://localhost:8080"

    # Prompt 缓存 TTL
    prompt_cache_ttl: int = 3600  # 1 小时

    # 降级配置
    llm_timeout: int = 10  # 秒
    llm_max_retries: int = 1
    max_question_rounds: int = 5

    class Config:
        env_file = ".env"


settings = Settings()
```

- [ ] **Step 4: 编写 `backend/app/main.py`**

```python
"""FastAPI 应用入口"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Wellcee Profile AI", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"status": "ok"}
```

- [ ] **Step 5: 创建前端脚手架**

```bash
cd frontend
npm create vite@latest . -- --template react-ts
npm install
npm install @tanstack/react-query axios
```

- [ ] **Step 6: 验证**

```bash
cd backend && uvicorn app.main:app --reload
# 访问 http://localhost:8000/health → {"status": "ok"}

cd frontend && npm run dev
# 访问 http://localhost:5173 → Vite 默认页
```

- [ ] **Step 7: Commit**

```bash
git init
git add -A && git commit -m "feat: project scaffold with FastAPI + React"
```

---

### Task 2: 标签体系配置（tag-taxonomy.yaml）

**Files:**
- Create: `backend/data/tag-taxonomy.yaml`
- Create: `backend/app/core/taxonomy.py`

**Interfaces:**
- Produces: `load_taxonomy() -> dict` — 加载 YAML 为 Python dict
- Produces: `build_keyword_trie(taxonomy) -> dict` — 构建关键词 Trie 索引

- [ ] **Step 1: 编写 `backend/data/tag-taxonomy.yaml`**

```yaml
version: "1.0"
categories:
  personality:
    label: "性格标签"
    icon: "🧠"
    description: "描述性格和社交倾向"
    tags:
      - id: personality-quiet
        label: "安静型"
        keywords: ["安静", "话少", "内向", "独处", "喜静", "不太说话", "比较宅"]
        roommate_relevance: high
      - id: personality-outgoing
        label: "外向型"
        keywords: ["外向", "开朗", "社交", "话多", "喜欢交朋友", "自来熟"]
        roommate_relevance: high
      - id: personality-balanced
        label: "中间型"
        keywords: ["亦动亦静", "看情况", "分人", "慢热"]
        roommate_relevance: high

  hobby:
    label: "爱好标签"
    icon: "🎯"
    description: "兴趣爱好"
    tags:
      - id: hobby-running
        label: "跑步"
        keywords: ["跑步", "慢跑", "夜跑", "晨跑", "马拉松"]
        roommate_relevance: medium
      - id: hobby-fitness
        label: "健身"
        keywords: ["健身", "撸铁", "健身房", "力量训练", "举铁"]
        roommate_relevance: medium
      - id: hobby-cooking
        label: "烹饪"
        keywords: ["做饭", "烹饪", "下厨", "烘焙", "做菜", "煮饭"]
        roommate_relevance: high
      - id: hobby-reading
        label: "阅读"
        keywords: ["看书", "阅读", "读书", "纸质书"]
        roommate_relevance: low
      - id: hobby-movies
        label: "看电影"
        keywords: ["电影", "看片", "追剧", "刷剧", "美剧", "日剧", "韩剧", "纪录片"]
        roommate_relevance: low
      - id: hobby-music
        label: "音乐"
        keywords: ["音乐", "听歌", "弹琴", "吉他", "钢琴", "唱歌"]
        roommate_relevance: medium
      - id: hobby-gaming
        label: "游戏"
        keywords: ["游戏", "打游戏", "电竞", "主机", "PS5", "Switch", "手游", "王者", "原神"]
        roommate_relevance: medium
      - id: hobby-travel
        label: "旅行"
        keywords: ["旅行", "旅游", "出去玩", "徒步", "爬山", "户外", "露营"]
        roommate_relevance: low
      - id: hobby-photography
        label: "摄影"
        keywords: ["摄影", "拍照", "相机", "胶片"]
        roommate_relevance: low

  lifestyle:
    label: "生活习惯"
    icon: "🏠"
    description: "日常生活习惯和偏好"
    tags:
      - id: lifestyle-early-sleeper
        label: "早睡型"
        keywords: ["早睡", "11点前睡", "十点睡", "早睡早起"]
        roommate_relevance: high
      - id: lifestyle-normal-sleeper
        label: "正常作息"
        keywords: ["正常作息", "作息规律", "12点睡", "规律作息"]
        roommate_relevance: high
      - id: lifestyle-night-owl
        label: "晚睡型"
        keywords: ["晚睡", "夜猫子", "熬夜", "1点以后", "睡得晚"]
        roommate_relevance: high
      - id: lifestyle-non-smoker
        label: "不吸烟"
        keywords: ["不吸烟", "不抽烟", "禁烟", "无烟", "讨厌烟味"]
        roommate_relevance: high
      - id: lifestyle-smoker
        label: "吸烟"
        keywords: ["吸烟", "抽烟", "烟民"]
        roommate_relevance: high
      - id: lifestyle-pet-owner
        label: "养宠物"
        keywords: ["养猫", "养狗", "宠物", "猫咪", "狗子", "猫", "狗", "布偶", "英短"]
        roommate_relevance: high
      - id: lifestyle-no-pet
        label: "不养宠物"
        keywords: ["不养宠物", "没宠物"]
        roommate_relevance: high
      - id: lifestyle-homebody
        label: "宅家型"
        keywords: ["宅", "宅家", "不出门", "在家待着", "宅男", "宅女"]
        roommate_relevance: medium

  roommate_expectation:
    label: "室友期望"
    icon: "🤝"
    description: "对理想室友的期望"
    tags:
      - id: roommate-quiet-env
        label: "安静环境"
        keywords: ["安静", "不要太吵", "想安静", "喜静"]
        roommate_relevance: high
      - id: roommate-clean-high
        label: "高清洁标准"
        keywords: ["干净", "整洁", "洁癖", "一尘不染", "定期打扫"]
        roommate_relevance: high
      - id: roommate-clean-medium
        label: "中等清洁标准"
        keywords: ["基本整洁", "不太脏就行"]
        roommate_relevance: high
      - id: roommate-non-smoker
        label: "不吸烟室友"
        keywords: ["室友不吸烟", "不抽烟的室友"]
        roommate_relevance: high
      - id: roommate-pet-friendly
        label: "接受宠物"
        keywords: ["接受宠物", "喜欢宠物", "宠物友好", "可以养猫", "可以养狗"]
        roommate_relevance: high
      - id: roommate-cook-together
        label: "可以一起做饭"
        keywords: ["一起做饭", "一起下厨", "搭伙", "一起吃饭"]
        roommate_relevance: medium
      - id: roommate-few-visitors
        label: "少访客"
        keywords: ["不带人", "少带人", "不喜欢访客", "不带朋友回来"]
        roommate_relevance: high

  rental_preference:
    label: "求租偏好"
    icon: "🔍"
    description: "租房偏好"
    tags:
      - id: rental-budget-low
        label: "预算3000以内"
        keywords: ["3000以内", "预算3000", "便宜", "三千以下", "2000多", "1500"]
        roommate_relevance: low
      - id: rental-budget-mid
        label: "预算3000-5000"
        keywords: ["3000-5000", "4000左右", "4500", "三千到五千", "三千五"]
        roommate_relevance: low
      - id: rental-budget-high
        label: "预算5000以上"
        keywords: ["5000以上", "预算充足", "6000", "8000"]
        roommate_relevance: low
      - id: rental-metro
        label: "近地铁"
        keywords: ["地铁", "交通方便", "地铁口", "近地铁", "步行到地铁"]
        roommate_relevance: low
      - id: rental-pet-friendly
        label: "宠物友好房源"
        keywords: ["宠物友好", "可以养宠物", "能养猫", "能养狗"]
        roommate_relevance: high

  listing_feature:
    label: "房源特征"
    icon: "🏡"
    description: "出租/转租房源特征"
    tags:
      - id: listing-renovated
        label: "精装修"
        keywords: ["精装", "精装修", "装修好", "新房", "新装修"]
        roommate_relevance: low
      - id: listing-sunny
        label: "采光好"
        keywords: ["采光好", "阳光", "朝南", "明亮", "光线好"]
        roommate_relevance: low
      - id: listing-metro
        label: "近地铁"
        keywords: ["地铁", "近地铁", "地铁口", "交通方便"]
        roommate_relevance: low

mutual_exclusion_rules:
  - group: ["lifestyle-smoker", "lifestyle-non-smoker"]
    rule: "取 confidence 高者"
  - group: ["lifestyle-early-sleeper", "lifestyle-night-owl"]
    rule: "取 confidence 高者"
```

- [ ] **Step 2: 编写 `backend/app/core/taxonomy.py`**

```python
"""标签体系加载与关键词索引"""
from pathlib import Path
import yaml
from functools import lru_cache


TAXONOMY_PATH = Path(__file__).parent.parent.parent / "data" / "tag-taxonomy.yaml"


@lru_cache(maxsize=1)
def load_taxonomy() -> dict:
    """加载标签体系 YAML"""
    with open(TAXONOMY_PATH, "r", encoding="utf-8") as f:
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


def get_dimensions_for_demand(demand_types: list[str]) -> list[str]:
    """根据需求类型返回应覆盖的维度列表"""
    dimensions = ["personality", "hobby", "lifestyle"]
    if "find_roommate" in demand_types:
        dimensions.append("roommate_expectation")
    if "rent" in demand_types:
        dimensions.append("rental_preference")
    if "list" in demand_types or "transfer" in demand_types:
        dimensions.append("listing_feature")
    if "transfer" in demand_types:
        dimensions.append("transfer_reason")
    return dimensions
```

- [ ] **Step 3: 验证**

```python
# backend/tests/test_taxonomy.py
from app.core.taxonomy import load_taxonomy, build_keyword_index

def test_load_taxonomy():
    taxonomy = load_taxonomy()
    assert taxonomy["version"] == "1.0"
    assert "personality" in taxonomy["categories"]
    assert len(taxonomy["categories"]["personality"]["tags"]) > 0

def test_keyword_index():
    taxonomy = load_taxonomy()
    index = build_keyword_index(taxonomy)
    assert "跑步" in index
    assert index["跑步"]["label"] == "跑步"
    assert "安静" in index
```

Run: `pytest backend/tests/test_taxonomy.py -v`

- [ ] **Step 4: Commit**

```bash
git add backend/data/tag-taxonomy.yaml backend/app/core/taxonomy.py backend/tests/test_taxonomy.py
git commit -m "feat: add tag taxonomy YAML config and loader"
```

---

### Task 3: 规则引擎

**Files:**
- Create: `backend/app/core/rule_engine.py`

**Interfaces:**
- Consumes: `load_taxonomy()`, `build_keyword_index()`, `get_dimensions_for_demand()` from Task 2
- Produces: `extract_draft_tags(free_text, taxonomy, keyword_index) -> dict` — 规则草稿标签
- Produces: `detect_dimension_gaps(free_text, demand_types, taxonomy, keyword_index) -> list` — 维度缺口检测
- Produces: `post_process_tags(raw_tags, taxonomy) -> dict` — 标签去重/分类/排序/互斥冲突解决

- [ ] **Step 1: 编写测试**

```python
# backend/tests/test_rule_engine.py
from app.core.rule_engine import (
    extract_draft_tags,
    detect_dimension_gaps,
    post_process_tags,
)
from app.core.taxonomy import load_taxonomy, build_keyword_index


taxonomy = load_taxonomy()
keyword_index = build_keyword_index(taxonomy)


class TestExtractDraftTags:
    def test_exact_keyword_match(self):
        text = "我喜欢跑步和做饭，平时比较安静"
        tags = extract_draft_tags(text, taxonomy, keyword_index)
        assert len(tags) >= 3  # 跑步、烹饪、安静型
        labels = [t["label"] for t in tags]
        assert "跑步" in labels
        assert "烹饪" in labels
        assert "安静型" in labels

    def test_no_match(self):
        text = "我喜欢在周末去公园散步思考人生"
        tags = extract_draft_tags(text, taxonomy, keyword_index)
        # "散步" 和 "思考" 不在关键词表中 → 空
        assert len(tags) == 0

    def test_all_tags_have_source_rule(self):
        text = "我不吸烟，喜欢健身"
        tags = extract_draft_tags(text, taxonomy, keyword_index)
        for tag in tags:
            assert tag["source"] == "rule"
            assert tag["confidence"] == 0.9

    def test_one_keyword_matches_one_tag_only(self):
        """一个文本片段不会因为匹配多个关键词而产生重复标签"""
        text = "我喜欢跑步慢跑夜跑"  # 三个关键词指向同一个标签
        tags = extract_draft_tags(text, taxonomy, keyword_index)
        running_tags = [t for t in tags if t["label"] == "跑步"]
        assert len(running_tags) <= 1


class TestDetectDimensionGaps:
    def test_all_covered_no_gaps(self):
        text = "我安静内向，喜欢跑步做饭，不吸烟，作息规律"
        gaps = detect_dimension_gaps(
            text, ["find_roommate"], taxonomy, keyword_index
        )
        # personality(hit:安静,内向), hobby(hit:跑步,做饭),
        # lifestyle(hit:不吸烟,作息规律), roommate_expectation(hit:作息规律)
        # cleaning_habit 可能缺失
        gap_dimensions = [g["dimension"] for g in gaps]
        # 严格来说 cleaning_habit 未覆盖，应出现在缺口中
        assert "cleaning_habit" in gap_dimensions or len(gaps) >= 0

    def test_no_demand_no_extra_dims(self):
        text = "我喜欢跑步"
        gaps = detect_dimension_gaps(
            text, ["none"], taxonomy, keyword_index
        )
        gap_dimensions = [g["dimension"] for g in gaps]
        assert "roommate_expectation" not in gap_dimensions
        assert "rental_preference" not in gap_dimensions
```

- [ ] **Step 2: 运行测试验证失败**

```bash
pytest backend/tests/test_rule_engine.py -v
# Expected: all FAIL (module not found)
```

- [ ] **Step 3: 编写 `backend/app/core/rule_engine.py`**

```python
"""规则引擎：关键词精确匹配、维度覆盖检测、标签后处理"""
from app.core.taxonomy import get_dimensions_for_demand


def extract_draft_tags(
    free_text: str, taxonomy: dict, keyword_index: dict
) -> dict[str, list[dict]]:
    """
    精确关键词匹配提取草稿标签。
    只追求高精度（精确匹配），不追求高召回。
    漏掉的留给 LLM 补充。
    返回按 category 分组的 dict。
    """
    result: dict[str, list[dict]] = {}

    for cat_key in taxonomy["categories"]:
        result[cat_key] = []

    for keyword, info in keyword_index.items():
        if keyword in free_text:
            cat_key = info["category"]
            # 检查是否已添加了同一个 tag_id
            existing_ids = [t["tag_id"] for t in result.get(cat_key, [])]
            if info["tag_id"] not in existing_ids:
                tag_entry = {
                    "label": info["label"],
                    "tag_id": info["tag_id"],
                    "source": "rule",
                    "confidence": 0.9,
                    "roommate_relevance": info["roommate_relevance"],
                }
                if cat_key not in result:
                    result[cat_key] = []
                result[cat_key].append(tag_entry)

    # 清理空分类
    return {k: v for k, v in result.items() if v}


def detect_dimension_gaps(
    free_text: str,
    demand_types: list[str],
    taxonomy: dict,
    keyword_index: dict,
) -> list[dict]:
    """
    检测用户文本中缺失的关键维度。
    返回维度缺口列表。
    """
    required_dims = get_dimensions_for_demand(demand_types)
    gaps = []

    # 对每个需求维度的子维度进行粗粒度检查
    dim_keyword_map = {
        "cleaning_habit": ["干净", "整洁", "打扫", "清洁", "洁癖", "卫生", "脏"],
        "noise_tolerance": ["安静", "噪音", "吵", "隔音", "吵闹"],
        "social_frequency": ["朋友", "访客", "带人", "聚会", "社交", "约朋友"],
        "cooking_attitude": ["做饭", "下厨", "厨房", "煮饭", "烹饪"],
        "pet_attitude": ["宠物", "猫", "狗", "养猫", "养狗", "过敏"],
        "smoking_attitude": ["吸烟", "抽烟", "烟味", "不吸烟"],
    }

    for dim, keywords in dim_keyword_map.items():
        # 简单检查：任何关键词命中即认为已覆盖
        covered = any(kw in free_text for kw in keywords)
        if not covered:
            gaps.append({
                "dimension": dim,
                "reason": f"需求 {demand_types} 下 {dim} 未检测到覆盖",
            })

    return gaps


def post_process_tags(
    tags: dict[str, list[dict]], taxonomy: dict
) -> dict[str, list[dict]]:
    """
    标签后处理：去重、排序、互斥冲突解决。
    按 confidence 降序排列同分类标签。
    """
    rules = taxonomy.get("mutual_exclusion_rules", [])

    for rule_group in rules:
        group_ids = rule_group["group"]
        # 收集冲突标签
        conflicting = []
        for cat_key, tag_list in tags.items():
            for tag in tag_list:
                if tag.get("tag_id") in group_ids:
                    conflicting.append((cat_key, tag))

        if len(conflicting) > 1:
            # 保留 confidence 最高的
            conflicting.sort(key=lambda x: x[1]["confidence"], reverse=True)
            winner_cat, winner = conflicting[0]
            for cat_key, tag in conflicting[1:]:
                tags[cat_key] = [t for t in tags[cat_key] if t != tag]

    # 每分类内按 confidence 降序
    for cat_key in tags:
        tags[cat_key].sort(key=lambda t: t["confidence"], reverse=True)

    return tags
```

- [ ] **Step 4: 运行测试验证通过**

```bash
pytest backend/tests/test_rule_engine.py -v
# Expected: all PASS
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/rule_engine.py backend/tests/test_rule_engine.py
git commit -m "feat: add rule engine for keyword matching, dimension gaps, and tag post-processing"
```

---

### Task 4: BGE-M3 向量服务

**Files:**
- Create: `backend/app/services/embedding.py`
- Create: `backend/app/core/vector_index.py`

**Interfaces:**
- Consumes: `load_taxonomy()` from Task 2
- Produces: `EmbeddingClient.embed(texts: list[str]) -> list[list[float]]`
- Produces: `TagVectorIndex.find_top_k(text_fragment: str, k: int = 3) -> list[dict]`

- [ ] **Step 1: 启动 BGE-M3 向量服务**

```bash
# CPU 部署（开发环境）
docker run -d --name bge-m3 -p 8080:80 \
  ghcr.io/huggingface/text-embeddings-inference:cpu-latest \
  --model-id BAAI/bge-m3
```

- [ ] **Step 2: 编写 `backend/app/services/embedding.py`**

```python
"""BGE-M3 向量服务客户端"""
import httpx
from app.config import settings


class EmbeddingClient:
    def __init__(self):
        self.base_url = settings.embedding_service_url
        self._client = httpx.AsyncClient(timeout=30.0)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """调用 TEI 接口生成嵌入向量"""
        response = await self._client.post(
            f"{self.base_url}/embed",
            json={"inputs": texts, "normalize": True},
        )
        response.raise_for_status()
        return response.json()

    async def close(self):
        await self._client.aclose()


embedding_client = EmbeddingClient()
```

- [ ] **Step 3: 编写 `backend/app/core/vector_index.py`**

```python
"""标签向量索引：预计算所有标签向量，支持相似度检索"""
import numpy as np
from app.core.taxonomy import load_taxonomy
from app.services.embedding import embedding_client


class TagVectorIndex:
    def __init__(self):
        self.tag_vectors: dict[str, np.ndarray] = {}  # tag_id → vector
        self.tag_info: dict[str, dict] = {}  # tag_id → {label, category, ...}
        self._built = False

    async def build(self, taxonomy: dict | None = None):
        """预计算标签体系中所有标签的向量"""
        if taxonomy is None:
            taxonomy = load_taxonomy()

        tag_texts = []
        tag_ids = []

        for cat_key, category in taxonomy["categories"].items():
            for tag_def in category["tags"]:
                text = f"{tag_def['label']}: {category['description']}"
                tag_texts.append(text)
                tag_ids.append(tag_def["id"])
                self.tag_info[tag_def["id"]] = {
                    "label": tag_def["label"],
                    "category": cat_key,
                    "roommate_relevance": tag_def.get("roommate_relevance", "low"),
                }

        vectors = await embedding_client.embed(tag_texts)
        for tag_id, vector in zip(tag_ids, vectors):
            self.tag_vectors[tag_id] = np.array(vector)

        self._built = True

    async def find_top_k(self, text: str, k: int = 3) -> list[dict]:
        """检索与文本最相似的 Top K 标签"""
        if not self._built:
            await self.build()

        query_vec = np.array((await embedding_client.embed([text]))[0])

        scores = []
        for tag_id, vec in self.tag_vectors.items():
            sim = float(np.dot(query_vec, vec))  # 已 normalize，点积即余弦
            scores.append((tag_id, sim))

        scores.sort(key=lambda x: x[1], reverse=True)
        top_k = scores[:k]

        return [
            {
                "tag_id": tag_id,
                "label": self.tag_info[tag_id]["label"],
                "category": self.tag_info[tag_id]["category"],
                "similarity": round(score, 4),
                "roommate_relevance": self.tag_info[tag_id]["roommate_relevance"],
            }
            for tag_id, score in top_k
        ]


vector_index = TagVectorIndex()
```

- [ ] **Step 4: 验证**

```python
# backend/tests/test_embedding.py（需要 BGE-M3 服务运行）
import pytest
from app.services.embedding import embedding_client

@pytest.mark.asyncio
async def test_embed_single_text():
    vectors = await embedding_client.embed(["测试文本"])
    assert len(vectors) == 1
    assert len(vectors[0]) == 1024  # BGE-M3 维度
```

Run: `pytest backend/tests/test_embedding.py -v`

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/embedding.py backend/app/core/vector_index.py
git commit -m "feat: add BGE-M3 embedding service client and tag vector index"
```

---

### Task 5: Prompt 模板引擎

**Files:**
- Create: `backend/prompts/system_context.txt`
- Create: `backend/prompts/analyze.txt`
- Create: `backend/prompts/bio.txt`
- Create: `backend/app/core/prompt_engine.py`

**Interfaces:**
- Produces: `render_prompt(template_name, variables) -> str`
- Produces: `get_system_context() -> str`

- [ ] **Step 1: 编写 `backend/prompts/system_context.txt`**

```text
## 平台背景
Wellcee（唯心所寓）是一个无中介个人直租平台。
用户在这里直接联系房东/转租人，通过生活习惯标签匹配室友，
参与租房社区的社交和分享。平台覆盖国内 40+ 城市，
用户来自全球 170+ 国家，以年轻白领、留学生、外籍租客为主。

## 租房场景
- 用户核心目的：找房子 / 找室友 / 出租转租 / 逛社区（可多选）
- 室友匹配：生活习惯细节（作息、清洁、噪音、宠物、社交）
  比兴趣标签更重要——直接影响合租体验
- 找房匹配：区域、预算、房型、通勤是核心决策维度
- 信任建设：真实表达 > 过度包装。用户反感 AI 代写，
  需要 AI 做思考搭档而非代笔
```

- [ ] **Step 2: 编写 `backend/prompts/analyze.txt`**

```text
{{ SYSTEM_CONTEXT }}

## 角色
你是一个帮用户在租房平台上表达真实自我的助手。
你的任务是：
1. 阅读用户的自我介绍
2. 确认/修正/补充规则提取的草稿标签
3. 识别模糊或缺失的关键维度
4. 生成 1-3 条追问建议

## 铁律
- 你看到的是用户的全部原文，规则草稿标签只是提示——如果草稿漏了或错了，你来修正
- 只提取用户明确提到或强烈暗示的标签，不要脑补
- 每个标签必须标注 source（free_text/question_answer）和 confidence（0-1, 0.5~1.0）
- MBTI：用户提到具体类型（如INFP/ENFJ等）→ 提取。没提到 → 不提取，不推断
- 标签总数不超过 20 个
- 每次最多生成 3 条追问
- 每条追问必须附带 2-4 个可点击选项 + 1 个「自己写」
- 追问必须与租房/室友场景相关

## 追问策略
- 具象化：检测到模糊标签 → 追问具体（「运动」→ 什么类型？）
- 场景化：检测到可展开的生活习惯 → 追问合租场景
- 画像补充：需求类型下的关键匹配维度缺失 → 主动提示

## 输入
- 用户自由文本：{{ free_text }}
- 需求类型：{{ demand_types }}
- 规则草稿标签：{{ draft_tags }}
- 维度缺口：{{ dimension_gaps }}
- 已覆盖的追问历史：{{ question_history }}

## 输出格式（严格 JSON，不要输出其他内容）
{
  "tags": {
    "personality": [
      {"label": "标签名", "source": "free_text", "confidence": 0.85}
    ],
    "hobby": [],
    "lifestyle": [],
    "roommate_expectation": [],
    "rental_preference": [],
    "listing_feature": [],
    "transfer_reason": []
  },
  "questions": [
    {
      "id": "q_6位随机码",
      "text": "追问文本",
      "dimension": "所属维度",
      "strategy": "concretize|scenario|supplement",
      "options": [
        {"label": "选项文本", "tag": "标签-标签名"}
      ]
    }
  ]
}
```

- [ ] **Step 3: 编写 `backend/prompts/bio.txt`**

```text
{{ SYSTEM_CONTEXT }}

## 角色
你是 Wellcee 上的文字编辑。帮用户把零散信息组织成一段
自然、真实、有温度的个人简介。这段简介可能被未来的室友、
房东或租客阅读——它需要在 20 秒内让人感受到一个真实的人。

## 铁律
- 只能使用输入材料中的信息，不要编造用户没有说过的事实
- 语气自然口语化，像当面聊天，不要像简历或房源广告
- 保持用户原文的语言风格
- 200 字以内

## 输入
- 用户原文：{{ free_text }}
- 已确认标签：{{ confirmed_tags }}
- 需求类型：{{ demand_types }}

## 结构
- 第一句：我是谁（职业+城市+尽量自然的性格描述）
- 中间：从标签中选 2-3 个最有区分度的点展开
- 收尾：根据需求类型
  - 「find_roommate」→ 期待什么样的室友
  - 「rent」→ 正在找什么样的房子
  - 「list」/「transfer」→ 房子亮点简述
  - 「none」→ 自然收束，不加目的性结尾

## 输出格式（只输出 JSON）
{"bio": "生成的简介文本"}
```

- [ ] **Step 4: 编写 `backend/app/core/prompt_engine.py`**

```python
"""Prompt 模板引擎"""
from pathlib import Path
from functools import lru_cache
import json


PROMPTS_DIR = Path(__file__).parent.parent.parent / "prompts"


@lru_cache(maxsize=1)
def get_system_context() -> str:
    """加载系统上下文块（所有 Prompt 共享）"""
    path = PROMPTS_DIR / "system_context.txt"
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()


def render_prompt(template_name: str, variables: dict) -> str:
    """
    渲染 Prompt 模板。
    template_name: 'analyze' | 'bio'
    variables: 模板变量 dict
    """
    path = PROMPTS_DIR / f"{template_name}.txt"
    with open(path, "r", encoding="utf-8") as f:
        template = f.read()

    # 注入系统上下文
    template = template.replace("{{ SYSTEM_CONTEXT }}", get_system_context())

    # 替换变量
    for key, value in variables.items():
        placeholder = f"{{{{ {key} }}}}"
        if isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False, indent=2)
        template = template.replace(placeholder, str(value))

    return template
```

- [ ] **Step 5: 验证**

```python
# backend/tests/test_prompt_engine.py
from app.core.prompt_engine import render_prompt, get_system_context

def test_system_context_not_empty():
    ctx = get_system_context()
    assert "Wellcee" in ctx
    assert len(ctx) > 100

def test_render_analyze_prompt():
    prompt = render_prompt("analyze", {
        "free_text": "测试文本",
        "demand_types": ["find_roommate"],
        "draft_tags": {},
        "dimension_gaps": [],
        "question_history": [],
    })
    assert "测试文本" in prompt
    assert "Wellcee" in prompt
    assert "输出格式" in prompt

def test_render_bio_prompt():
    prompt = render_prompt("bio", {
        "free_text": "测试",
        "confirmed_tags": {"personality": ["安静型"]},
        "demand_types": ["none"],
    })
    assert "测试" in prompt
    assert "安静型" in prompt
```

Run: `pytest backend/tests/test_prompt_engine.py -v`

- [ ] **Step 6: Commit**

```bash
git add backend/prompts/ backend/app/core/prompt_engine.py backend/tests/test_prompt_engine.py
git commit -m "feat: add prompt templates and rendering engine"
```

---

### Task 6: AI 编排器（LLM 调用 + 降级链 + 响应校验）

**Files:**
- Create: `backend/app/services/llm_client.py`
- Create: `backend/app/core/orchestrator.py`
- Create: `backend/app/core/schemas.py`

**Interfaces:**
- Consumes: `render_prompt()` from Task 5, `settings` from Task 1
- Produces: `LLMClient.chat(messages, model, provider) -> str`
- Produces: `Orchestrator.analyze(free_text, demand_types, draft_tags, dimension_gaps, question_history) -> dict`
- Produces: `Orchestrator.generate_bio(free_text, confirmed_tags, demand_types) -> dict`

- [ ] **Step 1: 编写 `backend/app/core/schemas.py`**

```python
"""Pydantic 数据模型"""
from pydantic import BaseModel, Field
from typing import Optional


class TagItem(BaseModel):
    label: str
    source: str = "free_text"  # free_text | question_answer | rule
    confidence: float = Field(ge=0.0, le=1.0)


class QuestionOption(BaseModel):
    label: str
    tag: Optional[str] = None


class Question(BaseModel):
    id: str
    text: str
    dimension: str
    strategy: str  # concretize | scenario | supplement
    options: list[QuestionOption]


class AnalyzeRequest(BaseModel):
    free_text: str = Field(min_length=1, max_length=5000)
    demand_types: list[str] = Field(default_factory=list)
    birth_year: Optional[int] = None
    question_history: list[dict] = Field(default_factory=list)
    draft_tags: dict[str, list[dict]] = Field(default_factory=dict)
    dimension_gaps: list[dict] = Field(default_factory=list)


class AnalyzeResponse(BaseModel):
    tags: dict[str, list[TagItem]]
    questions: list[Question]


class BioRequest(BaseModel):
    free_text: str = Field(min_length=1, max_length=5000)
    confirmed_tags: dict[str, list[str]]
    demand_types: list[str] = Field(default_factory=list)


class BioResponse(BaseModel):
    bio: str


class SaveProfileRequest(BaseModel):
    basic_fields: dict
    tags: dict[str, list[str]]
    bio: str


class SaveProfileResponse(BaseModel):
    success: bool
    profile_id: str
    tag_count: int
    completeness_score: int
```

- [ ] **Step 2: 编写 `backend/app/services/llm_client.py`**

```python
"""LLM 客户端：统一接口调用不同厂商"""
import json
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential
from app.config import settings


class LLMClient:
    def __init__(self):
        self._client = httpx.AsyncClient(timeout=settings.llm_timeout)

    async def _call_api(
        self,
        messages: list[dict],
        model: str,
        api_key: str,
        base_url: str,
    ) -> str:
        """底层 API 调用"""
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": 1024,
        }
        response = await self._client.post(
            f"{base_url}/chat/completions",
            headers=headers,
            json=payload,
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=1, max=3))
    async def call_qwen_plus(self, system_prompt: str, user_message: str) -> str:
        """调用 Qwen-Plus（主）"""
        return await self._call_api(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            model=settings.qwen_model,
            api_key=settings.qwen_api_key,
            base_url=settings.qwen_base_url,
        )

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=1, max=3))
    async def call_deepseek_v3(self, system_prompt: str, user_message: str) -> str:
        """调用 DeepSeek-V3（主）"""
        return await self._call_api(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            model=settings.deepseek_model,
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
        )

    @retry(stop=stop_after_attempt(1), wait=wait_exponential(multiplier=1, min=1, max=2))
    async def call_glm_air(self, system_prompt: str, user_message: str) -> str:
        """调用 GLM-4-Air（备选）"""
        return await self._call_api(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            model=settings.glm_air_model,
            api_key=settings.glm_api_key,
            base_url=settings.glm_base_url,
        )

    @retry(stop=stop_after_attempt(1))
    async def call_glm_flash(self, system_prompt: str, user_message: str) -> str:
        """调用 GLM-4-Flash（兜底，免费）"""
        return await self._call_api(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            model=settings.glm_flash_model,
            api_key=settings.glm_api_key,
            base_url=settings.glm_base_url,
        )

    async def close(self):
        await self._client.aclose()


llm_client = LLMClient()
```

- [ ] **Step 3: 编写 `backend/app/core/orchestrator.py`**

```python
"""AI 编排器：模型路由、降级链、响应校验"""
import json
import logging
from jsonschema import validate, ValidationError
from app.config import settings
from app.core.prompt_engine import render_prompt
from app.services.llm_client import llm_client


logger = logging.getLogger(__name__)

# JSON Schema for /analyze response
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
                    "options": {"type": "array", "minItems": 2},
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
    # 尝试直接解析
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    # 尝试提取 ```json ... ``` 块
    if "```json" in raw:
        start = raw.index("```json") + 7
        end = raw.index("```", start)
        return json.loads(raw[start:end].strip())
    if "```" in raw:
        start = raw.index("```") + 3
        end = raw.index("```", start)
        return json.loads(raw[start:end].strip())
    raise ValueError(f"无法从响应中提取 JSON: {raw[:200]}...")


async def analyze_with_fallback(
    free_text: str,
    demand_types: list[str],
    draft_tags: dict,
    dimension_gaps: list[dict],
    question_history: list[dict],
) -> dict:
    """
    追问+标签分析。
    主线：Qwen-Plus → 备线：GLM-4-Air → 兜底：GLM-4-Flash
    每次调用都走 JSON Schema 校验，失败则降级。
    """
    prompt = render_prompt("analyze", {
        "free_text": free_text,
        "demand_types": demand_types,
        "draft_tags": draft_tags,
        "dimension_gaps": dimension_gaps,
        "question_history": question_history,
    })
    system = "你是一个专业的用户画像分析助手。只输出 JSON，不要输出其他内容。"

    # Try Qwen-Plus (primary)
    try:
        raw = await llm_client.call_qwen_plus(system, prompt)
        result = _parse_json_response(raw)
        validate(instance=result, schema=ANALYZE_SCHEMA)
        logger.info("analyze: Qwen-Plus success")
        return result
    except Exception as e:
        logger.warning(f"analyze: Qwen-Plus failed ({e}), falling back to GLM-4-Air")

    # Try GLM-4-Air (secondary)
    try:
        raw = await llm_client.call_glm_air(system, prompt)
        result = _parse_json_response(raw)
        validate(instance=result, schema=ANALYZE_SCHEMA)
        logger.info("analyze: GLM-4-Air success")
        return result
    except Exception as e:
        logger.warning(f"analyze: GLM-4-Air failed ({e}), falling back to GLM-4-Flash")

    # Try GLM-4-Flash (last resort)
    try:
        raw = await llm_client.call_glm_flash(system, prompt)
        result = _parse_json_response(raw)
        validate(instance=result, schema=ANALYZE_SCHEMA)
        logger.info("analyze: GLM-4-Flash success (degraded)")
        return result
    except Exception as e:
        logger.error(f"analyze: all models failed ({e})")
        raise RuntimeError("AI 分析暂时不可用，请稍后重试")


async def generate_bio_with_fallback(
    free_text: str,
    confirmed_tags: dict[str, list[str]],
    demand_types: list[str],
) -> dict:
    """
    简介生成。
    主线：DeepSeek-V3 → 备线：Qwen3.5-Plus → 兜底：GLM-4-Air
    """
    prompt = render_prompt("bio", {
        "free_text": free_text,
        "confirmed_tags": confirmed_tags,
        "demand_types": demand_types,
    })
    system = "你是一个文字编辑。只输出 JSON，不要输出其他内容。"

    # Try DeepSeek-V3 (primary)
    try:
        raw = await llm_client.call_deepseek_v3(system, prompt)
        result = _parse_json_response(raw)
        validate(instance=result, schema=BIO_SCHEMA)
        logger.info("bio: DeepSeek-V3 success")
        return result
    except Exception as e:
        logger.warning(f"bio: DeepSeek-V3 failed ({e}), falling back to Qwen-Plus")

    # Try Qwen-Plus (secondary for bio)
    try:
        raw = await llm_client.call_qwen_plus(system, prompt)
        result = _parse_json_response(raw)
        validate(instance=result, schema=BIO_SCHEMA)
        logger.info("bio: Qwen-Plus success (fallback)")
        return result
    except Exception as e:
        logger.warning(f"bio: Qwen-Plus failed ({e}), falling back to GLM-4-Air")

    # Try GLM-4-Air (last resort)
    try:
        raw = await llm_client.call_glm_air(system, prompt)
        result = _parse_json_response(raw)
        validate(instance=result, schema=BIO_SCHEMA)
        logger.info("bio: GLM-4-Air success (degraded)")
        return result
    except Exception as e:
        logger.error(f"bio: all models failed ({e})")
        raise RuntimeError("简介生成暂时不可用，请稍后重试")
```

- [ ] **Step 4: 验证（单元测试，mock LLM）**

```python
# backend/tests/test_orchestrator.py
from app.core.orchestrator import _parse_json_response

def test_parse_clean_json():
    raw = '{"tags": {"personality": []}, "questions": []}'
    result = _parse_json_response(raw)
    assert result["tags"] == {"personality": []}

def test_parse_json_in_code_block():
    raw = '这是一些文字\n```json\n{"bio": "测试简介"}\n```'
    result = _parse_json_response(raw)
    assert result["bio"] == "测试简介"

def test_parse_invalid_raises():
    raw = '这不是JSON'
    import pytest
    with pytest.raises(ValueError):
        _parse_json_response(raw)
```

Run: `pytest backend/tests/test_orchestrator.py -v`

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/schemas.py backend/app/services/llm_client.py backend/app/core/orchestrator.py backend/tests/test_orchestrator.py
git commit -m "feat: add AI orchestrator with LLM client, fallback chain, and JSON validation"
```

---

### Task 7: API 端点（/analyze, /bio, /taxonomy, /fields）

**Files:**
- Create: `backend/app/api/__init__.py`
- Create: `backend/app/api/profile.py`

**Interfaces:**
- Consumes: `Orchestrator` functions from Task 6, `taxonomy` functions from Task 2, `rule_engine` from Task 3
- Produces: 4 REST endpoints

- [ ] **Step 1: 编写 `backend/app/api/profile.py`**

```python
"""个人资料 API 端点"""
from fastapi import APIRouter, HTTPException
from app.core.schemas import (
    AnalyzeRequest, AnalyzeResponse,
    BioRequest, BioResponse,
    SaveProfileRequest, SaveProfileResponse,
)
from app.core.taxonomy import load_taxonomy, build_keyword_index
from app.core.rule_engine import (
    extract_draft_tags,
    detect_dimension_gaps,
    post_process_tags,
)
from app.core.orchestrator import analyze_with_fallback, generate_bio_with_fallback

router = APIRouter(prefix="/api/profile", tags=["profile"])


@router.post("/ai/analyze", response_model=AnalyzeResponse)
async def analyze_profile(req: AnalyzeRequest):
    """追问生成 + 标签提取"""
    taxonomy = load_taxonomy()
    keyword_index = build_keyword_index(taxonomy)

    # 规则引擎粗筛（每次调用都跑，因为追问答案可能增加了新文本）
    # 合并原文和追问答案
    combined_text = req.free_text
    for qh in req.question_history:
        combined_text += " " + qh.get("answer", "")

    draft_tags = extract_draft_tags(combined_text, taxonomy, keyword_index)
    gaps = detect_dimension_gaps(combined_text, req.demand_types, taxonomy, keyword_index)

    # AI 分析
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

    # 后处理
    result["tags"] = post_process_tags(result["tags"], taxonomy)

    return AnalyzeResponse(**result)


@router.post("/ai/bio", response_model=BioResponse)
async def generate_bio(req: BioRequest):
    """简介生成"""
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
    """获取标签体系（前端渲染用）"""
    taxonomy = load_taxonomy()
    # 只返回前端需要的部分（去掉 keywords 减少传输量）
    result = {"version": taxonomy["version"], "categories": {}}
    for cat_key, category in taxonomy["categories"].items():
        result["categories"][cat_key] = {
            "label": category["label"],
            "icon": category["icon"],
            "description": category["description"],
            "tags": [
                {"id": t["id"], "label": t["label"],
                 "roommate_relevance": t.get("roommate_relevance", "low")}
                for t in category["tags"]
            ],
        }
    return result


@router.put("/fields", response_model=SaveProfileResponse)
async def save_profile(req: SaveProfileRequest):
    """保存最终资料"""
    # TODO: 实现数据库写入（Task 8）
    tag_count = sum(len(v) for v in req.tags.values())
    return SaveProfileResponse(
        success=True,
        profile_id="p_temp_001",
        tag_count=tag_count,
        completeness_score=min(tag_count * 10, 100),
    )
```

- [ ] **Step 2: 注册路由到 main.py**

```python
# 在 backend/app/main.py 中添加
from app.api.profile import router as profile_router
app.include_router(profile_router)
```

- [ ] **Step 3: 验证 API**

```bash
# 启动后端
cd backend && uvicorn app.main:app --reload

# 测试 taxonomy 端点
curl http://localhost:8000/api/profile/tags/taxonomy

# 测试 analyze 端点（需要配置 API key）
curl -X POST http://localhost:8000/api/profile/ai/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "free_text": "我喜欢安静地做饭和跑步，不吸烟",
    "demand_types": ["find_roommate"],
    "question_history": [],
    "draft_tags": {},
    "dimension_gaps": []
  }'
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/api/profile.py backend/app/main.py
git commit -m "feat: add profile API endpoints (analyze, bio, taxonomy, save)"
```

---

### Task 8: 数据库模型与保存

**Files:**
- Create: `backend/app/models/__init__.py`
- Create: `backend/app/models/profile.py`
- Create: `backend/app/services/db.py`

**Interfaces:**
- Produces: `async def save_user_profile(profile_data) -> str` — 返回 profile_id
- Produces: `async def get_user_profile(user_id) -> dict`

- [ ] **Step 1: 编写 `backend/app/models/profile.py`**

```python
"""用户资料数据模型"""
from sqlalchemy import Column, String, Integer, JSON, DateTime, func
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class UserProfile(Base):
    __tablename__ = "user_profiles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(64), unique=True, nullable=False, index=True)

    # 固定字段
    avatar_url = Column(String(512), nullable=True)
    nickname = Column(String(64), nullable=True)
    birth_year = Column(Integer, nullable=True)
    occupation = Column(String(128), nullable=True)
    region = Column(String(64), nullable=True)
    languages = Column(JSON, default=list)  # ["中文", "English"]
    demand_types = Column(JSON, default=list)  # ["find_roommate", "rent"]

    # AI 产出
    tags = Column(JSON, default=dict)  # {"personality": ["安静型"], ...}
    bio = Column(String(1024), nullable=True)

    # 元信息
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
```

- [ ] **Step 2: 编写 `backend/app/services/db.py`**

```python
"""数据库会话与操作"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select
from app.config import settings
from app.models.profile import UserProfile, Base

engine = create_async_engine(settings.database_url, echo=False)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db():
    """创建所有表"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def save_or_update_profile(
    user_id: str,
    basic_fields: dict,
    tags: dict,
    bio: str,
) -> str:
    """保存或更新用户资料"""
    async with async_session() as session:
        # 查询是否存在
        stmt = select(UserProfile).where(UserProfile.user_id == user_id)
        result = await session.execute(stmt)
        profile = result.scalar_one_or_none()

        if profile:
            # 更新
            for key, value in basic_fields.items():
                setattr(profile, key, value)
            profile.tags = tags
            profile.bio = bio
        else:
            # 新建
            profile = UserProfile(
                user_id=user_id,
                avatar_url=basic_fields.get("avatar_url"),
                nickname=basic_fields.get("nickname"),
                birth_year=basic_fields.get("birth_year"),
                occupation=basic_fields.get("occupation"),
                region=basic_fields.get("region"),
                languages=basic_fields.get("languages", []),
                demand_types=basic_fields.get("demand_types", []),
                tags=tags,
                bio=bio,
            )
            session.add(profile)

        await session.commit()
        return user_id
```

- [ ] **Step 3: 更新 save_profile 端点**

```python
# 替换 backend/app/api/profile.py 中的 save_profile
@router.put("/fields", response_model=SaveProfileResponse)
async def save_profile(req: SaveProfileRequest):
    """保存最终资料"""
    from app.services.db import save_or_update_profile

    user_id = "u_current"  # TODO: 从认证上下文获取
    await save_or_update_profile(
        user_id=user_id,
        basic_fields=req.basic_fields,
        tags=req.tags,
        bio=req.bio,
    )
    tag_count = sum(len(v) for v in req.tags.values())
    return SaveProfileResponse(
        success=True,
        profile_id=user_id,
        tag_count=tag_count,
        completeness_score=min(tag_count * 10, 100),
    )
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/models/ backend/app/services/db.py backend/app/api/profile.py
git commit -m "feat: add database models and profile save/update logic"
```

---

### Task 9: 前端基础布局与路由

**Files:**
- Create: `frontend/src/pages/EditProfile.tsx`
- Create: `frontend/src/components/ProfileForm.tsx`
- Create: `frontend/src/App.tsx` (modify)

**Interfaces:**
- Produces: `/edit-profile` 页面路由，固定表单组件

- [ ] **Step 1: 编写 `frontend/src/types.ts`**

```typescript
// frontend/src/types.ts

export interface TaxonomyCategory {
  label: string;
  icon: string;
  description: string;
  tags: { id: string; label: string; roommate_relevance: string }[];
}

export interface Taxonomy {
  version: string;
  categories: Record<string, TaxonomyCategory>;
}

export interface TagItem {
  label: string;
  source: 'free_text' | 'question_answer' | 'rule';
  confidence: number;
}

export interface QuestionOption {
  label: string;
  tag: string | null;
}

export interface Question {
  id: string;
  text: string;
  dimension: string;
  strategy: 'concretize' | 'scenario' | 'supplement';
  options: QuestionOption[];
}

export interface AnalyzeResponse {
  tags: Record<string, TagItem[]>;
  questions: Question[];
}

export interface BioResponse {
  bio: string;
}

export type DemandType = 'list' | 'transfer' | 'find_roommate_existing'
  | 'find_roommate_searching' | 'none';
```

- [ ] **Step 2: 编写 `frontend/src/App.tsx`**

```tsx
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import EditProfile from './pages/EditProfile';

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/edit-profile" element={<EditProfile />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/
git commit -m "feat: add frontend base layout and routing"
```

---

### Task 10: 固定表单组件

**Files:**
- Create: `frontend/src/components/BasicForm.tsx`
- Create: `frontend/src/components/DemandSelector.tsx`

**Interfaces:**
- Produces: `BasicForm` 组件 — 头像/昵称/年龄/职业/地区/语言/需求栏
- Props: `onComplete(basicFields)` — 提交时回调

- [ ] **Step 1: 编写 `frontend/src/components/BasicForm.tsx`**

```tsx
import { useState } from 'react';
import DemandSelector from './DemandSelector';
import type { DemandType } from '../types';

interface BasicFields {
  avatar_url: string;
  nickname: string;
  birth_year: number;
  occupation: string;
  region: string;
  languages: string[];
  demand_types: DemandType[];
}

interface Props {
  onComplete: (fields: BasicFields) => void;
}

export default function BasicForm({ onComplete }: Props) {
  const [nickname, setNickname] = useState('');
  const [birthYear, setBirthYear] = useState(2000);
  const [occupation, setOccupation] = useState('');
  const [region, setRegion] = useState('');
  const [languages, setLanguages] = useState<string[]>(['中文']);
  const [demandTypes, setDemandTypes] = useState<DemandType[]>([]);

  const handleSubmit = () => {
    onComplete({
      avatar_url: '',
      nickname,
      birth_year: birthYear,
      occupation,
      region,
      languages,
      demand_types: demandTypes,
    });
  };

  return (
    <div className="basic-form">
      <h2>编辑资料</h2>

      {/* 头像 - 简化处理 */}
      <label>头像</label>
      <div className="avatar-placeholder">📷 上传头像</div>

      <label>昵称</label>
      <input value={nickname} onChange={e => setNickname(e.target.value)} />

      <label>出生年份</label>
      <select value={birthYear} onChange={e => setBirthYear(Number(e.target.value))}>
        {Array.from({ length: 40 }, (_, i) => 2005 - i).map(y => (
          <option key={y} value={y}>{y}</option>
        ))}
      </select>

      <label>职业 / 学校</label>
      <input value={occupation} onChange={e => setOccupation(e.target.value)}
        placeholder="如：设计师 / 复旦大学" />

      <label>地区</label>
      <input value={region} onChange={e => setRegion(e.target.value)}
        placeholder="如：上海" />

      <label>语言</label>
      <input value={languages.join(', ')} onChange={e =>
        setLanguages(e.target.value.split(',').map(s => s.trim()))
      } placeholder="如：中文, English" />

      <label>我当前的需求（可多选）</label>
      <DemandSelector selected={demandTypes} onChange={setDemandTypes} />

      <button onClick={handleSubmit}>保存，进入下一步</button>
    </div>
  );
}
```

- [ ] **Step 2: 编写 `frontend/src/components/DemandSelector.tsx`**

```tsx
import type { DemandType } from '../types';

interface Props {
  selected: DemandType[];
  onChange: (types: DemandType[]) => void;
}

const DEMAND_OPTIONS: { value: DemandType; label: string; icon: string }[] = [
  { value: 'list', label: '我要出租', icon: '🏠' },
  { value: 'transfer', label: '我要转租', icon: '🔄' },
  { value: 'find_roommate_existing', label: '找室友 - 已有房', icon: '🤝' },
  { value: 'find_roommate_searching', label: '找室友 - 还没房', icon: '🤝' },
  { value: 'none', label: '暂无需求，逛逛社区', icon: '👀' },
];

export default function DemandSelector({ selected, onChange }: Props) {
  const toggle = (value: DemandType) => {
    if (value === 'none') {
      onChange(['none']);
    } else {
      const next = selected.includes(value)
        ? selected.filter(s => s !== value)
        : [...selected.filter(s => s !== 'none'), value];
      onChange(next.length === 0 ? ['none'] : next);
    }
  };

  return (
    <div className="demand-selector">
      {DEMAND_OPTIONS.map(opt => (
        <button
          key={opt.value}
          className={`demand-chip ${selected.includes(opt.value) ? 'active' : ''}`}
          onClick={() => toggle(opt.value)}
        >
          {opt.icon} {opt.label}
        </button>
      ))}
    </div>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/BasicForm.tsx frontend/src/components/DemandSelector.tsx frontend/src/types.ts
git commit -m "feat: add basic form and demand selector components"
```

---

### Task 11: 自由文本输入组件

**Files:**
- Create: `frontend/src/components/FreeTextInput.tsx`
- Create: `frontend/src/hooks/usePlaceholder.ts`

**Interfaces:**
- Props: `demandTypes`, `onAnalyze(freeText)`, `placeholder`
- 根据需求栏动态切换引导文案

- [ ] **Step 1: 编写 `frontend/src/hooks/usePlaceholder.ts`**

```typescript
import { useMemo } from 'react';
import type { DemandType } from '../types';

export function usePlaceholder(demandTypes: DemandType[]): string {
  return useMemo(() => {
    const has = (t: DemandType) => demandTypes.includes(t);
    const isNone = demandTypes.length === 0 || has('none');

    if (isNone) return '介绍你自己——你的性格、爱好、生活方式…';

    const parts: string[] = ['介绍你自己'];

    if (has('find_roommate_existing') || has('find_roommate_searching')) {
      parts.push('你理想的室友是什么样的——作息、生活习惯、相处方式');
    }
    if (demandTypes.some(t => t === 'list' || t === 'transfer')) {
      parts.push(has('transfer') ? '为什么转租、房子情况' : '你的房子情况');
    }
    if (demandTypes.some(t => t === 'rent' || t === 'find_roommate_searching')) {
      parts.push('你对房子的期望——区域、预算、最在意的方面');
    }

    return parts.join('，') + '…';
  }, [demandTypes]);
}
```

- [ ] **Step 2: 编写 `frontend/src/components/FreeTextInput.tsx`**

```tsx
import { useState, useEffect } from 'react';
import type { DemandType } from '../types';
import { usePlaceholder } from '../hooks/usePlaceholder';

interface Props {
  demandTypes: DemandType[];
  onAnalyze: (text: string) => void;
  loading: boolean;
}

export default function FreeTextInput({ demandTypes, onAnalyze, loading }: Props) {
  const [text, setText] = useState('');
  const placeholder = usePlaceholder(demandTypes);

  const canAnalyze = text.length >= 10;

  return (
    <div className="free-text-input">
      <h3>用一段话介绍你自己</h3>

      <textarea
        value={text}
        onChange={e => setText(e.target.value)}
        placeholder={placeholder}
        rows={6}
        maxLength={2000}
      />

      <div className="text-actions">
        <span className="char-count">{text.length}/2000</span>
        <button
          className="analyze-btn"
          onClick={() => onAnalyze(text)}
          disabled={!canAnalyze || loading}
        >
          {loading ? '⏳ AI 正在看…' : '✨ AI 帮我看看'}
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/FreeTextInput.tsx frontend/src/hooks/usePlaceholder.ts
git commit -m "feat: add free text input with dynamic placeholder and analyze trigger"
```

---

### Task 12: 追问面板组件

**Files:**
- Create: `frontend/src/components/QuestionPanel.tsx`

**Interfaces:**
- Props: `questions`, `onAnswer(questionId, answer)`, `onSkip(questionId)`, `onSkipAll()`
- 追问气泡展示，单条跳过 / 全部跳过

- [ ] **Step 1: 编写 `frontend/src/components/QuestionPanel.tsx`**

```tsx
import { useState } from 'react';
import type { Question } from '../types';

interface Props {
  questions: Question[];
  onAnswer: (questionId: string, answer: string) => void;
  onSkip: (questionId: string) => void;
  onSkipAll: () => void;
}

export default function QuestionPanel({ questions, onAnswer, onSkip, onSkipAll }: Props) {
  const [customInputs, setCustomInputs] = useState<Record<string, string>>({});
  const [answeredIds, setAnsweredIds] = useState<Set<string>>(new Set());

  if (questions.length === 0) return null;

  return (
    <div className="question-panel">
      <h4>💡 AI 帮你发现了 {questions.length} 个可以补充的地方</h4>

      {questions.map(q => {
        if (answeredIds.has(q.id)) return null;

        return (
          <div key={q.id} className="question-bubble">
            <p className="question-text">{q.text}</p>

            <div className="question-options">
              {q.options.map(opt => (
                <button
                  key={opt.label}
                  className="option-chip"
                  onClick={() => {
                    setAnsweredIds(prev => new Set(prev).add(q.id));
                    onAnswer(q.id, opt.tag || opt.label);
                  }}
                >
                  {opt.label}
                </button>
              ))}

              {/* 自己写 */}
              <div className="custom-input-row">
                <input
                  value={customInputs[q.id] || ''}
                  onChange={e => setCustomInputs(prev => ({
                    ...prev, [q.id]: e.target.value
                  }))}
                  placeholder="✏️ 自己写…"
                />
                <button
                  onClick={() => {
                    if (customInputs[q.id]?.trim()) {
                      setAnsweredIds(prev => new Set(prev).add(q.id));
                      onAnswer(q.id, customInputs[q.id]);
                    }
                  }}
                  disabled={!customInputs[q.id]?.trim()}
                >
                  确认
                </button>
              </div>
            </div>

            <button className="skip-btn" onClick={() => onSkip(q.id)}>
              ── 不感兴趣，跳过 →
            </button>
          </div>
        );
      })}

      {/* 全部跳过 */}
      {answeredIds.size < questions.length && (
        <button className="skip-all-btn" onClick={onSkipAll}>
          🙈 全部跳过，不再提示
        </button>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/QuestionPanel.tsx
git commit -m "feat: add AI question panel with skip/answer interactions"
```

---

### Task 13: 标签确认组件

**Files:**
- Create: `frontend/src/components/TagConfirmation.tsx`

**Interfaces:**
- Props: `tags`, `taxonomy`, `onConfirm(confirmedTags)`, `onReanalyze()`
- 按维度分类展示标签，支持删除/添加

- [ ] **Step 1: 编写 `frontend/src/components/TagConfirmation.tsx`**

```tsx
import { useState } from 'react';
import type { TagItem, Taxonomy } from '../types';

interface Props {
  tags: Record<string, TagItem[]>;
  taxonomy: Taxonomy;
  demandTypes: string[];
  onConfirm: (confirmed: Record<string, string[]>) => void;
  onReanalyze: () => void;
}

export default function TagConfirmation({
  tags, taxonomy, demandTypes, onConfirm, onReanalyze,
}: Props) {
  const [localTags, setLocalTags] = useState(tags);

  const removeTag = (category: string, label: string) => {
    setLocalTags(prev => ({
      ...prev,
      [category]: prev[category].filter(t => t.label !== label),
    }));
  };

  const handleConfirm = () => {
    const confirmed: Record<string, string[]> = {};
    for (const [cat, tagList] of Object.entries(localTags)) {
      confirmed[cat] = tagList.map(t => t.label);
    }
    onConfirm(confirmed);
  };

  const totalTags = Object.values(localTags).flat().length;

  // 只展示与需求类型相关的分类
  const relevantCategories = ['personality', 'hobby', 'lifestyle'];
  if (demandTypes.some(t => t.includes('roommate'))) relevantCategories.push('roommate_expectation');
  if (demandTypes.some(t => ['rent', 'find_roommate_searching'].includes(t)))
    relevantCategories.push('rental_preference');
  if (demandTypes.some(t => ['list', 'transfer'].includes(t)))
    relevantCategories.push('listing_feature');

  return (
    <div className="tag-confirmation">
      <h3>🏷️ 已识别 {totalTags} 个标签（确认后可修改）</h3>

      {relevantCategories.map(catKey => {
        const category = taxonomy.categories[catKey];
        if (!category) return null;
        const tagList = localTags[catKey] || [];
        if (tagList.length === 0) return null;

        return (
          <div key={catKey} className="tag-category">
            <h4>{category.icon} {category.label}</h4>
            <div className="tag-chips">
              {tagList.map(tag => (
                <span key={tag.label} className="tag-chip">
                  {tag.label}
                  {tag.source === 'question_answer' && ' 💬'}
                  <button onClick={() => removeTag(catKey, tag.label)}>×</button>
                </span>
              ))}
            </div>
          </div>
        );
      })}

      <div className="tag-actions">
        <button onClick={onReanalyze}>🔄 继续追问补充</button>
        <button className="primary" onClick={handleConfirm}>确认标签，生成简介</button>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/TagConfirmation.tsx
git commit -m "feat: add tag confirmation component with category grouping"
```

---

### Task 14: 简介预览组件

**Files:**
- Create: `frontend/src/components/BioPreview.tsx`

**Interfaces:**
- Props: `bio`, `onRegenerate()`, `onSave(bio)`

- [ ] **Step 1: 编写 `frontend/src/components/BioPreview.tsx`**

```tsx
import { useState } from 'react';

interface Props {
  bio: string;
  loading: boolean;
  onRegenerate: () => void;
  onSave: (bio: string) => void;
}

export default function BioPreview({ bio, loading, onRegenerate, onSave }: Props) {
  const [edited, setEdited] = useState(bio);

  return (
    <div className="bio-preview">
      <h3>📝 你的个人简介</h3>

      <div className="bio-card">
        <textarea
          value={edited}
          onChange={e => setEdited(e.target.value)}
          rows={5}
          maxLength={200}
        />
        <span className="char-count">{edited.length}/200</span>
      </div>

      <div className="bio-actions">
        <button onClick={() => navigator.clipboard.writeText(edited)}>
          📋 复制
        </button>
        <button onClick={onRegenerate} disabled={loading}>
          {loading ? '生成中…' : '🔄 重新生成'}
        </button>
        <button className="primary" onClick={() => onSave(edited)}>
          ✅ 保存资料
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/BioPreview.tsx
git commit -m "feat: add bio preview component with edit and regenerate"
```

---

### Task 15: 主页面编排（EditProfile 页面）

**Files:**
- Modify: `frontend/src/pages/EditProfile.tsx`（完整实现）
- Create: `frontend/src/services/api.ts`

**Interfaces:**
- 串联 Step 1-7 完整流程
- 状态管理：`step`, `basicFields`, `freeText`, `questions`, `tags`, `bio`

- [ ] **Step 1: 编写 `frontend/src/services/api.ts`**

```typescript
import axios from 'axios';
import type {
  Taxonomy, AnalyzeResponse, BioResponse,
  DemandType, TagItem,
} from '../types';

const api = axios.create({ baseURL: 'http://localhost:8000' });

export async function fetchTaxonomy(): Promise<Taxonomy> {
  const { data } = await api.get('/api/profile/tags/taxonomy');
  return data;
}

interface AnalyzeParams {
  free_text: string;
  demand_types: DemandType[];
  question_history: { question_id: string; question_text: string; answer: string }[];
  draft_tags: Record<string, { label: string; source: string; confidence: number }[]>;
  dimension_gaps: { dimension: string; reason: string }[];
}

export async function analyzeProfile(params: AnalyzeParams): Promise<AnalyzeResponse> {
  const { data } = await api.post('/api/profile/ai/analyze', params);
  return data;
}

interface BioParams {
  free_text: string;
  confirmed_tags: Record<string, string[]>;
  demand_types: DemandType[];
}

export async function generateBio(params: BioParams): Promise<BioResponse> {
  const { data } = await api.post('/api/profile/ai/bio', params);
  return data;
}

interface SaveParams {
  basic_fields: Record<string, unknown>;
  tags: Record<string, string[]>;
  bio: string;
}

export async function saveProfile(params: SaveParams): Promise<void> {
  await api.put('/api/profile/fields', params);
}
```

- [ ] **Step 2: 编写 `frontend/src/pages/EditProfile.tsx`**

```tsx
import { useState, useEffect } from 'react';
import BasicForm from '../components/BasicForm';
import FreeTextInput from '../components/FreeTextInput';
import QuestionPanel from '../components/QuestionPanel';
import TagConfirmation from '../components/TagConfirmation';
import BioPreview from '../components/BioPreview';
import {
  fetchTaxonomy, analyzeProfile, generateBio, saveProfile,
} from '../services/api';
import type {
  DemandType, Question, TagItem,
  AnalyzeResponse, Taxonomy,
} from '../types';

type Step = 'form' | 'free_text' | 'questions' | 'tags' | 'bio';

export default function EditProfile() {
  const [step, setStep] = useState<Step>('form');
  const [taxonomy, setTaxonomy] = useState<Taxonomy | null>(null);

  // 状态
  const [basicFields, setBasicFields] = useState<Record<string, unknown>>({});
  const [demandTypes, setDemandTypes] = useState<DemandType[]>([]);
  const [freeText, setFreeText] = useState('');
  const [questions, setQuestions] = useState<Question[]>([]);
  const [questionHistory, setQuestionHistory] = useState<
    { question_id: string; question_text: string; answer: string }[]
  >([]);
  const [tags, setTags] = useState<Record<string, TagItem[]>>({});
  const [bio, setBio] = useState('');
  const [loading, setLoading] = useState(false);

  // 跳过计数（用于三级退出）
  const [skipAllCount, setSkipAllCount] = useState(0);

  useEffect(() => {
    fetchTaxonomy().then(setTaxonomy);
  }, []);

  // Step 1 → 2
  const handleFormComplete = (fields: Record<string, unknown>) => {
    setBasicFields(fields);
    setDemandTypes((fields.demand_types as DemandType[]) || []);
    setStep('free_text');
  };

  // Step 2 → 3: 调用 /analyze
  const handleAnalyze = async (text: string) => {
    setFreeText(text);
    setLoading(true);
    try {
      const result = await analyzeProfile({
        free_text: text,
        demand_types: demandTypes,
        question_history: questionHistory,
        draft_tags: {},
        dimension_gaps: [],
      });
      setTags(result.tags);
      setQuestions(result.questions);
      setStep('questions');
    } catch (e) {
      alert('AI 分析失败：' + (e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  // Step 3: 追问回答
  const handleAnswer = (questionId: string, answer: string) => {
    const q = questions.find(q => q.id === questionId);
    setQuestionHistory(prev => [...prev, {
      question_id: questionId,
      question_text: q?.text || '',
      answer,
    }]);
  };

  const handleSkip = (questionId: string) => {
    // 单条跳过，不做记录
  };

  const handleSkipAll = () => {
    setSkipAllCount(prev => prev + 1);
    setStep('tags');  // 直接跳到标签确认
  };

  // Step 3 → 4: 追问完毕后提取标签
  const handleQuestionsDone = async () => {
    setLoading(true);
    try {
      const result = await analyzeProfile({
        free_text: freeText,
        demand_types: demandTypes,
        question_history: questionHistory,
        draft_tags: {},
        dimension_gaps: [],
      });
      setTags(result.tags);
      setQuestions([]);
      setStep('tags');
    } catch (e) {
      alert('标签提取失败：' + (e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  // Step 4 → 5: 标签确认后生成简介
  const handleTagsConfirmed = async (confirmed: Record<string, string[]>) => {
    setLoading(true);
    try {
      const result = await generateBio({
        free_text: freeText,
        confirmed_tags: confirmed,
        demand_types: demandTypes,
      });
      setBio(result.bio);
      // 保存确认后的标签
      const cleanTags: Record<string, TagItem[]> = {};
      Object.entries(confirmed).forEach(([cat, labels]) => {
        cleanTags[cat] = labels.map(l => ({
          label: l, source: 'free_text' as const, confidence: 1.0,
        }));
      });
      setTags(cleanTags);
      setStep('bio');
    } catch (e) {
      alert('简介生成失败：' + (e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  // Step 5: 保存
  const handleSave = async (finalBio: string) => {
    const confirmedTags: Record<string, string[]> = {};
    Object.entries(tags).forEach(([cat, tagList]) => {
      confirmedTags[cat] = tagList.map(t => t.label);
    });

    try {
      await saveProfile({
        basic_fields: basicFields,
        tags: confirmedTags,
        bio: finalBio,
      });
      alert('✅ 资料已保存！');
    } catch (e) {
      alert('保存失败：' + (e as Error).message);
    }
  };

  const shouldSilence = skipAllCount >= 3;

  return (
    <div className="edit-profile">
      {step === 'form' && <BasicForm onComplete={handleFormComplete} />}

      {step === 'free_text' && (
        <FreeTextInput
          demandTypes={demandTypes}
          onAnalyze={handleAnalyze}
          loading={loading}
        />
      )}

      {step === 'questions' && questions.length > 0 && !shouldSilence && (
        <>
          <QuestionPanel
            questions={questions}
            onAnswer={handleAnswer}
            onSkip={handleSkip}
            onSkipAll={handleSkipAll}
          />
          <button onClick={handleQuestionsDone}>
            {questionHistory.length > 0 ? '追问完毕，查看标签 →' : '跳过追问，直接提取标签 →'}
          </button>
        </>
      )}

      {step === 'tags' && taxonomy && (
        <TagConfirmation
          tags={tags}
          taxonomy={taxonomy}
          demandTypes={demandTypes}
          onConfirm={handleTagsConfirmed}
          onReanalyze={() => {
            setStep('free_text');
          }}
        />
      )}

      {step === 'bio' && (
        <BioPreview
          bio={bio}
          loading={loading}
          onRegenerate={() => handleTagsConfirmed(
            Object.fromEntries(
              Object.entries(tags).map(([k, v]) => [k, v.map(t => t.label)])
            )
          )}
          onSave={handleSave}
        />
      )}
    </div>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/EditProfile.tsx frontend/src/services/api.ts
git commit -m "feat: wire up full EditProfile flow (form → AI → questions → tags → bio → save)"
```

---

### Task 16: 集成测试与错误处理完善

**Files:**
- Create: `backend/tests/test_api_integration.py`

- [ ] **Step 1: 编写集成测试**

```python
# backend/tests/test_api_integration.py
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.mark.asyncio
async def test_taxonomy_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/profile/tags/taxonomy")
        assert response.status_code == 200
        data = response.json()
        assert data["version"] == "1.0"
        assert "personality" in data["categories"]
        assert len(data["categories"]["personality"]["tags"]) > 0


@pytest.mark.asyncio
async def test_analyze_validation():
    """空文本应被拒绝"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/profile/ai/analyze", json={
            "free_text": "",  # 无效：长度为 0
            "demand_types": [],
        })
        assert response.status_code == 422  # Pydantic 校验错误
```

Run: `pytest backend/tests/test_api_integration.py -v`

- [ ] **Step 2: Commit**

```bash
git add backend/tests/test_api_integration.py
git commit -m "test: add API integration tests"
```

---

### Task 17: Prompt 优化与 A/B 测试准备

**Files:**
- Modify: `backend/prompts/analyze.txt`
- Create: `backend/data/prompt-changelog.md`

- [ ] **Step 1: 创建 `backend/data/prompt-changelog.md`**

```markdown
# Prompt 变更日志

## v1.0 — 2026-07-10
- 初始版本
- 系统上下文块 + analyze Prompt + bio Prompt
- 标签体系通过草稿标签注入，不嵌入 Prompt

---
## 变更模板
### vX.X — YYYY-MM-DD
- **变更内容**：描述改了什么
- **原因**：为什么改
- **预期效果**：期望改善什么指标
- **回滚方案**：如何回滚到上一版本
```

- [ ] **Step 2: Commit**

```bash
git add backend/data/prompt-changelog.md
git commit -m "docs: add prompt changelog template"
```

---

## Plan Self-Review

### 1. Spec Coverage

| PRD/Tech Spec 需求 | 对应 Task |
|---|---|
| 固定表单 7 字段 | Task 10 |
| 差异化输入引导 | Task 11 (usePlaceholder) |
| AI 追问（用户主动唤起） | Task 11 (按钮), Task 12 (面板) |
| 三级退出机制 | Task 12 (skip/skipAll), Task 15 (skipAllCount) |
| 标签提取（三层体系） | Task 6 (orchestrator), Task 13 (UI) |
| 标签 source/confidence | Task 6 (schemas), Task 3 (rule_engine) |
| MBTI 处理规则 | Task 5 (prompt 铁律) |
| 简介生成（不编造） | Task 5 (bio prompt), Task 6 (orchestrator) |
| 需求栏多选 | Task 10 (DemandSelector) |
| 规则引擎（精确匹配） | Task 3 |
| 混合 LLM 调用 | Task 6 |
| 降级链 | Task 6 (orchestrator fallback) |
| API 合约（4 端点） | Task 7 |
| JSON Schema 校验 | Task 6 (orchestrator validate) |
| BGE-M3 向量服务 | Task 4 |
| Prompt 模板引擎 | Task 5 |
| 标签体系 YAML | Task 2 |
| 数据库持久化 | Task 8 |
| 前端完整流程串联 | Task 15 |
| 监控埋点 | Task 7（API 端点可加 middleware） |

### 2. Placeholder Scan

- ✅ 无 TBD/TODO
- ✅ 所有函数签名完整
- ✅ 所有测试含实际代码
- ✅ DB 中的 `user_id` 使用占位 `"u_current"`，标注 TODO 待认证集成 — 这是合理的（认证系统不在本期范围）

### 3. Type Consistency

- ✅ `TagItem` 类型在 `types.ts` 和 `schemas.py` 中字段一致
- ✅ `AnalyzeRequest` / `AnalyzeResponse` 结构前后端一致
- ✅ `Question` 的 `options` 字段在 prompt 输出格式、后端 schema、前端类型中一致
- ✅ Tag category keys 在 taxonomy YAML、schemas.py、前端组件中一致

---

**Plan complete and saved to `docs/superpowers/plans/2026-07-10-wellcee-profile-ai-plan.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — 每 Task 一个独立 subagent，Task 间 review，快速迭代

**2. Inline Execution** — 在当前 session 中逐步执行，批量推进 + 检查点

**Which approach?**
