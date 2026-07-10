# Wellcee（唯心所寓）— 个人资料 AI 增强完善流程

基于 LLM 的租房平台个人资料完善系统。用户在固定表单后自由输入自我介绍，AI 主动追问、提取标签、生成个人简介。

## 架构

```
用户自由文本
    ↓
规则引擎（关键词精确匹配，0 Token）
    ↓ 草稿标签 + 维度缺口
Qwen-Plus（LLM 看全文，确认/补充标签 + 生成追问）
    ↓ 用户确认标签
DeepSeek-V3（基于原文+标签生成自然简介）
    ↓
保存到数据库（SQLite / PostgreSQL）
```

## 技术栈

- **后端**：Python 3.11+, FastAPI, SQLAlchemy (async), Pydantic v2
- **AI**：Qwen-Plus + DeepSeek-V3（主线），GLM-4-Air / Flash（降级链）
- **数据库**：SQLite（本地开发），PostgreSQL（生产）

## 快速开始

### 1. 安装依赖

```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. 配置 API Key

```bash
cp .env.example .env
# 编辑 .env，填入至少一个 LLM 厂商的 API Key
```

### 3. 启动服务

```bash
uvicorn app.main:app --reload
# → http://localhost:8000
# → http://localhost:8000/docs  (Swagger UI)
```

### 4. 测试

```bash
# 健康检查
curl http://localhost:8000/health

# 获取标签体系
curl http://localhost:8000/api/profile/tags/taxonomy

# AI 分析（需要 API Key）
curl -X POST http://localhost:8000/api/profile/ai/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "free_text": "我在上海做设计，喜欢安静地跑步和做饭，不吸烟",
    "demand_types": ["find_roommate"]
  }'
```

## API 端点

| 方法 | 路径 | 用途 |
|------|------|------|
| POST | `/api/profile/ai/analyze` | 追问生成 + 标签提取 |
| POST | `/api/profile/ai/bio` | 个人简介生成 |
| GET | `/api/profile/tags/taxonomy` | 标签体系获取 |
| PUT | `/api/profile/fields` | 保存最终资料 |
| GET | `/health` | 健康检查 |

## 降级策略

主线 → 备线 → 免费兜底：

- 追问+标签：Qwen-Plus → GLM-4-Air → GLM-4-Flash
- 简介生成：DeepSeek-V3 → Qwen-Plus → GLM-4-Air

## 成本

| 步骤 | 模型 | 单次成本（估算） |
|------|------|:---:|
| 追问+标签 | Qwen-Plus | ~¥0.0014 |
| 简介生成 | DeepSeek-V3 | ~¥0.0026 |
| **合计** | | **~¥0.004** |

## 项目文件

```
backend/
├── app/
│   ├── main.py          # FastAPI 入口
│   ├── config.py        # 配置（环境变量）
│   ├── api/profile.py   # API 端点
│   ├── core/
│   │   ├── taxonomy.py  # 标签体系加载
│   │   ├── rule_engine.py # 规则引擎
│   │   ├── prompt_engine.py # Prompt 模板渲染
│   │   ├── orchestrator.py  # AI 编排 + 降级链
│   │   └── schemas.py   # Pydantic 模型
│   ├── services/
│   │   ├── llm_client.py # 多厂商 LLM 客户端
│   │   └── db.py        # 数据库操作
│   └── models/profile.py # 数据表模型
├── data/tag-taxonomy.yaml # 标签体系配置
├── prompts/              # Prompt 模板
└── requirements.txt
demo/
└── wellcee-profile-ai-mvp.html  # 交互 Demo
docs/superpowers/
├── specs/   # PRD + 技术方案
└── plans/   # 实施计划
```
