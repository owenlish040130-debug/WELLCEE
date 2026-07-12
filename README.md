# Wellcee（唯心所寓）— 个人资料 AI 增强完善流程

通过 AI 大模型让用户更便捷地完善个人资料，同时提升资料完整度和个性化表达。用户在固定表单后自由输入自我介绍（文字或语音），AI 智能追问、提取结构化标签、生成个人简介。

## Demo

👉 下载 `demo/wellcee-profile-ai-mvp.html`，浏览器直接打开即可体验交互流程。

> Demo 需要连接后端 API。本地启动后端后点击页面顶部「切换后端」输入地址；如果没有后端，Demo 仅展示界面流程。

## 快速开始

### 1. 安装依赖

```bash
cd backend
pip install -r requirements.txt
```

### 2. 配置 API Key

```bash
cp .env.example .env
```

编辑 `.env`，填入：

| 变量 | 说明 | 获取方式 |
|------|------|---------|
| `DEEPSEEK_API_KEY` | 必填，AI 追问+标签+简介 | platform.deepseek.com 注册 |
| `DASHSCOPE_API_KEY` | 选填，语音识别（阿里云免费36,000次） | dashscope.aliyun.com 注册 |

### 3. 启动

```bash
python -m uvicorn app.main:app --port 9000
# → http://localhost:9000
# → http://localhost:9000/docs  (Swagger)
```

### 4. 打开 Demo

浏览器打开 `demo/wellcee-profile-ai-mvp.html`，默认连 `localhost:9000`。

## AI 如何参与流程

| 环节 | 说明 |
|------|------|
| **智能引导** | 根据用户勾选的需求类型（找室友/求租/出租/转租），自由文本输入框引导文案动态切换 |
| **智能追问** | LLM 通读用户原文，识别模糊表述和缺失维度，生成引用用户原话的场景化追问；MBTI 未提及时展示全部 16 种类型供选择 |
| **标签生成** | 从原文和追问回答中提取结构化标签（性格/爱好/生活习惯/室友期望/求租偏好/房源特征），标注来源和置信度 |
| **简介生成** | 基于原文+确认标签，生成自然真实的个人简介（不编造事实） |

## API 端点

| 方法 | 路径 | 用途 |
|------|------|------|
| POST | `/api/profile/ai/analyze` | 追问生成 + 标签提取 |
| POST | `/api/profile/ai/bio` | 个人简介生成 |
| POST | `/api/profile/ai/transcribe` | 语音转文字 |
| GET | `/api/profile/tags/taxonomy` | 标签体系获取 |
| PUT | `/api/profile/fields` | 保存最终资料 |
| GET | `/health` | 健康检查 |

## 架构

```
用户自由文本 / 语音
    ↓
规则引擎 — 关键词匹配，0 Token
    ↓ 草稿标签 + 维度缺口
DeepSeek-V3 — LLM 看全文，标签提取 + 追问生成
    ↓ 用户确认标签
DeepSeek-V3 — 基于原文+标签生成自然简介
    ↓
保存到数据库（SQLite）
```

## 成本

| 步骤 | 模型 | 单次成本（估算） |
|------|------|:---:|
| 追问+标签 | DeepSeek-V3 | ~¥0.002 |
| 简介生成 | DeepSeek-V3 | ~¥0.002 |
| 语音识别 | 阿里云 Paraformer-v2 | 免费（36,000次额度） |
| **合计** | | **~¥0.004** |

## 项目结构

```
backend/
├── app/
│   ├── main.py              # FastAPI 入口
│   ├── config.py            # 环境变量配置
│   ├── api/profile.py       # REST API 端点
│   ├── core/
│   │   ├── taxonomy.py      # 标签体系 YAML 加载
│   │   ├── rule_engine.py   # 规则引擎
│   │   ├── prompt_engine.py # Prompt 模板渲染
│   │   ├── orchestrator.py  # AI 编排 + 降级链
│   │   └── schemas.py       # Pydantic 模型
│   ├── services/
│   │   ├── llm_client.py    # DeepSeek/GLM 客户端
│   │   ├── asr.py           # 阿里云语音识别
│   │   └── db.py            # SQLite 操作
│   └── models/profile.py    # 用户资料表
├── data/tag-taxonomy.yaml   # 80+ 标签定义
├── prompts/                 # Prompt 模板
└── requirements.txt
demo/
└── wellcee-profile-ai-mvp.html  # 交互 Demo（可独立运行）
docs/superpowers/
├── specs/   # PRD + 技术方案
└── plans/   # 实施计划
```
