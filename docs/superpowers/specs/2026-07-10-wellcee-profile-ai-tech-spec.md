# Wellcee 个人资料完善流程 AI 增强 — 技术方案文档

> 版本：v1.0
> 日期：2026-07-10
> 配套 PRD：[2026-07-10-wellcee-profile-ai-prd.md](./2026-07-10-wellcee-profile-ai-prd.md)

---

## 一、系统架构

### 1.1 总体架构图

```
┌─────────────────────────────────────────────────────────────┐
│                      前端 (Client)                           │
│                                                             │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────────┐  │
│  │ 固定表单  │  │ 自由文本  │  │ 追问面板  │  │ 标签确认   │  │
│  │ 组件      │  │ 输入组件  │  │ 组件      │  │ 组件       │  │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └─────┬──────┘  │
│       │              │             │               │         │
└───────┼──────────────┼─────────────┼───────────────┼─────────┘
        │              │             │               │
        ▼              ▼             ▼               ▼
┌─────────────────────────────────────────────────────────────┐
│                   后端 API 层 (REST)                          │
│                                                             │
│  POST /api/profile/ai/analyze    → AI 分析（追问+标签）      │
│  POST /api/profile/ai/bio        → 简介生成                  │
│  GET  /api/profile/tags/taxonomy → 标签体系获取              │
│  PUT  /api/profile/fields        → 保存最终资料              │
│                                                             │
└──────────────┬──────────────────────────────────────────────┘
               │
   ┌───────────┴───────────┐
   │                       │
   ▼                       ▼
┌──────────────┐   ┌──────────────────┐
│  规则引擎     │   │  AI 编排器        │
│              │   │                  │
│ - 维度覆盖检测│   │ - 模型路由        │
│ - 精确标签提取│   │ - 降级链管理      │
│ - 标签后处理  │   │ - Prompt 模板引擎 │
│ - 五行计算    │   │ - 响应校验        │
│              │   │                  │
│ 0 Token 成本  │   │                  │
└──────┬───────┘   └────────┬─────────┘
       │                    │
       │            ┌───────┴────────┐
       │            │                │
       │            ▼                ▼
       │     ┌────────────┐  ┌────────────┐
       │     │ Qwen-Plus  │  │ DeepSeek-V3│
       │     │ (小模型层)  │  │ (强模型层)  │
       │     └────────────┘  └────────────┘
       │            │ (主)          │ (主)
       │            │                │
       │     ┌──────┴────────┐      │
       │     │ 降级备选       │      │
       │     │ GLM-4-Air     │  Qwen3.5-Plus
       │     │ GLM-4-Flash   │  GLM-4-Air
       │     └───────────────┘      │
       │                            │
       ▼                            │
┌──────────────────────┐            │
│ BGE-M3 向量服务(本地) │            │
│                      │            │
│ - 标签候选检索        │            │
│ - 相似度计算          │            │
│ - 0 调用成本          │            │
└──────────────────────┘            │
                                    │
       ┌────────────────────────────┘
       ▼
┌──────────────────────┐
│ 标签体系配置          │
│ (tag-taxonomy.yaml)  │
│                      │
│ - 标签全集定义        │
│ - 分类层级            │
│ - 关键词映射          │
│ - 互斥规则            │
└──────────────────────┘
```

### 1.2 模块职责

| 模块 | 职责 | 技术栈 | Token 成本 |
|------|------|--------|:---:|
| 规则引擎 | 维度覆盖检测、精确关键词→标签映射、标签去重/分类/排序/互斥冲突解决、五行计算 | 纯 Python/Node.js 代码，< 200 行 | 0 |
| AI 编排器 | 模型路由、降级链管理、Prompt 模板渲染、响应 JSON Schema 校验、重试逻辑 | 后端服务层 | 0 |
| 小模型层 | 追问生成 + 模糊标签确认（合并为 1 次调用） | Qwen-Plus（主），GLM-4-Air（备） | ~¥0.0014/次 |
| 强模型层 | 个人简介生成 | DeepSeek-V3（主），Qwen3.5-Plus（备） | ~¥0.0026/次 |
| BGE-M3 向量服务 | 标签候选检索（模糊文本 → Top 3 候选标签相似度匹配） | 本地部署，TEI 框架 | 0 |
| 标签体系配置 | 标签全集、分类层级、关键词映射词典、互斥规则 | YAML 文件，前后端同源 | 0 |

### 1.3 核心设计原则

**LLM 主导理解 + 规则辅助提效**：LLM 看到用户全文进行主体理解，规则提前做「显性提取」作为草稿标签喂给 LLM 减负。规则追求高精度、放弃高召回——漏掉的 LLM 能补救。

**规则是 LLM 的「草稿助手」，不是「门卫」。**

---

## 二、LLM 调用架构

### 2.1 混合模式数据流

```
用户自由文本 + 需求类型
        │
        ▼
┌───────────────────────────────┐
│  Step 1: 规则引擎粗筛          │
│                               │
│  ① 维度覆盖检测（关键词词典）   │
│  ② 精确标签映射（Trie 匹配）   │
│  ③ 五行计算（出生年份→五行）    │
│                               │
│  输出：                        │
│  - draft_tags: 规则草稿标签    │
│  - dimension_gaps: 维度缺口    │
│  - 完整的用户全文（不裁剪）     │
│                               │
│  成本：0 Token                 │
└───────────┬───────────────────┘
            │ draft_tags + gaps
            ▼
┌───────────────────────────────┐
│  Step 2: Qwen-Plus（1 次调用）  │
│                               │
│  输入：用户全文 + 需求类型      │
│       + 规则草稿标签（提示）    │
│       + 维度缺口（提示）        │
│                               │
│  任务（合并）：                 │
│  ① 确认/修正/补充规则草稿标签   │
│  ② 识别规则遗漏的模糊表述       │
│  ③ 生成 1-3 条追问（带选项）   │
│                               │
│  输出：{tags: [...],          │
│         questions: [...]}     │
│                               │
│  Prompt: ~800 Token           │
│  成本：~¥0.0014                │
└───────────┬───────────────────┘
            │
    ┌───────┴───────┐
    ▼               ▼
 追问面板         标签初稿
（用户交互）      （前端暂存）
    │               │
    └───┬───────────┘
        ▼
  用户回答追问
        │
        ▼
┌───────────────────────────────┐
│  Step 3: 规则引擎增量更新      │
│                               │
│  追问选项 → 标签直接映射        │
│  「自己写」→ 标记为需重分析     │
│                               │
│  成本：几乎 0                  │
└───────────┬───────────────────┘
            │
            ▼
    用户确认/调整最终标签
            │
            ▼
┌───────────────────────────────┐
│  Step 4: DeepSeek-V3（1次调用） │
│                               │
│  输入：用户原文                │
│       + 已确认标签列表         │
│       + 需求类型               │
│                               │
│  任务：生成自然个人简介         │
│  输出：{bio: "..."}           │
│                               │
│  Prompt: ~500 Token           │
│  成本：~¥0.0026                │
└───────────────────────────────┘
```

### 2.2 调用次数对比

| | 原方案 B（链式 3 次） | 现方案（混合架构） |
|---|---|---|
| 强 LLM 调用 | 3 次 | **1 次**（仅简介） |
| 小/中 LLM 调用 | 0 | **1 次**（追问+标签合并） |
| 规则处理 | 0 | 覆盖 70%+ 确定性操作 |
| 单次估算成本 | ~¥0.03-0.05 | **~¥0.004** |

---

## 三、模型选型（详细分析与决策）

### 3.1 调研数据来源

基于 2025 年 7 月真实 API 文档和第三方评测数据（C-Eval、C-MTEB、OpenRouter、各厂商官网），进行横向对比。

### 3.2 候选模型能力矩阵

#### 3.2.1 中文能力与价格

| 模型 | 厂商 | 输入 ¥/百万Token | 输出 ¥/百万Token | C-Eval 中文 | 定位 |
|------|------|:---:|:---:|:---:|------|
| DeepSeek-V3 | DeepSeek | 2 | 8 | **87.6%** 🥇 | 通用旗舰 |
| DeepSeek-R1 | DeepSeek | 4 | 16 | 83.2% | 推理专用 |
| Qwen-Plus | 阿里云 | 0.8 | 2 | ~80%+ | 均衡性价比 |
| Qwen3.5-Plus | 阿里云 | 0.8 | 4.8 | ~82%+ | 新一代均衡 |
| Qwen-Max | 阿里云 | 11.2 | 44.8 | ~85%+ | 旗舰 |
| GLM-4-Air | 智谱 | ~1 | ~1 | — | 高性价比 |
| GLM-4-Flash | 智谱 | **免费** | **免费** | — | 轻量免费 |
| Kimi K2 Instruct | 月之暗面 | ~1 | ~17.5 | — | Agent 强 |

#### 3.2.2 DeepSeek-V3 vs R1 深度对比

| 维度 | V3 | R1 | 对本项目的影响 |
|------|:---:|:---:|------|
| **C-Eval 中文** | **87.6%** | 83.2% | V3 更适合中文生成 |
| 长文本摘要准确率 | **比 R1 高 15%** | — | 简介生成是摘要式任务 |
| 结构化 JSON 输出 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | 标签提取需要可靠 JSON |
| 多轮对话上下文 | 85%+（20轮） | — | 追问环节需要上下文理解 |
| 推理能力 | 中 | **强** | **本项目不需要复杂推理** |
| 价格（标准时段） | ¥2/¥8 | ¥4/¥16 | V3 便宜一半 |
| 价格（错峰） | ¥1/¥4 | ¥1/¥4 | 凌晨两者同价 |
| 幻觉率 | **低** | 高于 V3 | 简介生成不能编造事实 |

**结论**：V3 在中文生成、结构化输出、长文本摘要三个维度全面优于 R1，且价格仅一半。R1 的推理能力优势对本项目没有增益——我们不需要做数学题。

#### 3.2.3 结构化输出能力对比

本项目对 JSON 输出格式要求严格（标签列表、追问列表、选项列表）。综合调研数据：

| 模型 | JSON 结构化输出 | 格式偏离率（估计） |
|------|:---:|:---:|
| DeepSeek-V3 | ⭐⭐⭐⭐⭐ | < 2% |
| Qwen-Plus | ⭐⭐⭐⭐ | < 5% |
| GLM-4-Air | ⭐⭐⭐ | < 8% |
| GLM-4-Flash | ⭐⭐ | < 15% |

### 3.3 分层选型决策

#### 3.3.1 追问+标签层（小模型层）

**任务特征**：读取用户文本 → 确认/修正/补充规则草稿标签 → 识别模糊维度 → 生成追问 → 返回结构化 JSON。本质是**分类 + 简单生成**，不涉及复杂推理。

**选型要求（按优先级）**：
1. 中文语义理解（识别模糊表述、场景化理解）
2. 结构化 JSON 输出稳定性
3. 低延迟（用户等待感知 < 3 秒）
4. 低成本（高频调用，日活 × 人均调用次数）

**主选：通义千问 Qwen-Plus**

| 维度 | 评价 |
|------|------|
| 能力适配 | 定位即「中等复杂度任务」，中文理解+结构化输出能力胜任 |
| 成本 | ¥0.8/¥2 每百万Token，单次调用 ~¥0.0014 |
| 延迟 | < 2 秒（P95），用户感知可接受 |
| 生态 | 阿里云百炼平台，API 稳定、文档完善 |
| Prompt Cache | 支持，系统上下文可 100% 缓存 |

**备选：智谱 GLM-4-Air**

| 维度 | 评价 |
|------|------|
| 能力 | 对标 GPT-4o，中文 OK，结构化输出弱于 Qwen-Plus |
| 成本 | ~¥1/¥1 每百万Token，与 Qwen-Plus 接近 |
| 切换条件 | Qwen-Plus API 连续 3 次超时或 5xx → 自动切换 |

**兜底：智谱 GLM-4-Flash**

| 维度 | 评价 |
|------|------|
| 能力 | 轻量模型，结构化输出不稳定，仅限紧急降级 |
| 成本 | **完全免费** |
| 触发条件 | Qwen-Plus 和 GLM-4-Air 均不可用 |

#### 3.3.2 简介生成层（强模型层）

**任务特征**：将原文 + 确认标签合成为 200 字以内的自然中文个人简介。要求语气自然口语化、保持用户原文风格、根据需求类型调整收尾。本质是**自然语言生成 + 风格控制**。

**选型要求（按优先级）**：
1. 中文自然度与温度感（不能像机器翻译）
2. 忠实输入材料（不编造事实——幻觉率低）
3. 长文本理解与摘要能力

**主选：DeepSeek-V3**

| 维度 | 评价 |
|------|------|
| 能力适配 | C-Eval 中文 87.6%（调研全榜最高），长文本摘要准确率比 R1 高 15% |
| 为什么不是 R1 | R1 强在数学/代码/逻辑推理，对简介生成无增益；V3 中文更好且更便宜 |
| 成本 | ¥2/¥8 每百万Token，单次 ~¥0.0026；错峰时段半价 |
| 延迟 | < 5 秒（P95） |
| 幻觉率 | 低于 R1（关键——简介不能编造用户事实） |

**备选：通义千问 Qwen3.5-Plus**

| 维度 | 评价 |
|------|------|
| 能力 | 新一代均衡模型，中文优于旧 Qwen-Plus |
| 成本 | ¥0.8/¥4.8 每百万Token，比 V3 略便宜 |
| 切换条件 | DeepSeek-V3 不可用 → 自动切换 |

#### 3.3.3 嵌入向量层

**任务特征**：用户文本片段 → 计算与标签体系内所有标签向量的余弦相似度 → 返回 Top 3 候选标签。本质是**语义相似度检索**。

**选型：BAAI BGE-M3**

| 维度 | 评价 |
|------|------|
| 中文能力 | C-MTEB 综合 71.4，中文 Recall@5 0.783 |
| vs OpenAI | 中文 Recall 比 text-embedding-3-large 高 **8%** |
| 参数量 | 568M，1024 维输出 |
| 部署 | 本地 TEI 框架，支持 GPU/CPU/ONNX INT8 |
| 多粒度 | Dense + Sparse + Multi-Vector 三路输出，支持混合检索 |
| 成本 | **完全免费**（本地部署，无 API 调用费） |
| 硬件 | RTX 3060+ 即可（标签总数 < 1000，向量库极小） |

### 3.4 应急降级链

```
正常路径：
  追问+标签: Qwen-Plus ──→ 简介: DeepSeek-V3

Qwen-Plus 不可用：
  追问+标签: GLM-4-Air ──→ 简介: DeepSeek-V3

DeepSeek-V3 不可用：
  追问+标签: Qwen-Plus ──→ 简介: Qwen3.5-Plus

全不可用（极端）：
  追问+标签: GLM-4-Flash ──→ 简介: GLM-4-Air
  （功能降级提示用户「AI 服务暂时降级，建议稍后再试」）
```

### 3.5 成本估算

#### 单次完整流程

| 步骤 | 模型 | 输入 Token | 输出 Token | 输入 ¥ | 输出 ¥ | 小计 ¥ |
|------|------|:---:|:---:|:---:|:---:|:---:|
| 追问+标签（缓存命中） | Qwen-Plus | 200（动态） | 300 | 0.00016 | 0.0006 | 0.00076 |
| 追问+标签（缓存未命中） | Qwen-Plus | 800 | 300 | 0.00064 | 0.0006 | 0.00124 |
| 简介生成 | DeepSeek-V3 | 500 | 200 | 0.001 | 0.0016 | 0.0026 |
| 向量匹配 | BGE-M3（本地） | — | — | 0 | 0 | 0 |
| **单次合计（缓存命中）** | | | | | | **¥0.0034** |
| **单次合计（缓存未命中）** | | | | | | **¥0.0038** |

#### 规模化估算

| 日活用户数 | 日均调用次数* | 日成本（¥） | 月成本（¥） |
|:---:|:---:|:---:|:---:|
| 1,000 | 500 | ¥1.90 | ¥57 |
| 10,000 | 5,000 | ¥19 | ¥570 |
| 100,000 | 50,000 | ¥190 | ¥5,700 |

*假设 50% 的用户会走 AI 流程，每人平均 1 次

#### 错峰优惠进一步降本

凌晨 00:30-08:30 时段 DeepSeek V3 半价，简介生成成本从 ¥0.0026 降至 ¥0.0013，单次总成本降至 ~¥0.002。适合批量处理或非实时场景。

---

## 四、API 设计

### 4.1 接口清单

| 方法 | 路径 | 用途 | 调用的 AI 模型 |
|------|------|------|:---:|
| POST | `/api/profile/ai/analyze` | 追问生成 + 标签提取 | Qwen-Plus |
| POST | `/api/profile/ai/bio` | 个人简介生成 | DeepSeek-V3 |
| GET | `/api/profile/tags/taxonomy` | 获取标签体系 | 无（静态） |
| PUT | `/api/profile/fields` | 保存最终资料 | 无 |

### 4.2 API 调用模式说明

`/analyze` 端点支持**多轮调用**——前端可以在用户每次回答追问后重新调用，逐步积累标签：

```
第 1 轮：用户输入自由文本 → 调用 /analyze（question_history=[]）
         → 返回 tags（初稿）+ questions（追问列表）
         → 用户回答 2 条追问，跳过 1 条

第 2 轮：前端将答案填入 question_history → 再次调用 /analyze
         → 返回 tags（更新，融合了追问答案）+ questions（新追问，排除已回答维度）
         → 用户可以继续回答或跳过

...最多 5 轮（前端限制）

最后：用户确认最终标签 → 调用 /bio 生成简介
```

每次调用 `/analyze` 时，前端将用户已回答的所有追问填入 `question_history`，后端将其纳入分析上下文。已回答过的维度不会再次被追问。

### 4.3 POST /api/profile/ai/analyze

```
Request:
{
  "free_text": "我是在上海工作的设计师，平时喜欢安静地待在家里做饭看电影，偶尔跑步。希望找到作息规律、不吸烟的室友...",
  "demand_types": ["find_roommate", "rent"],
  "birth_year": 1998,
  "question_history": [
    {
      "question_id": "q_x1y2z3",
      "question_text": "说到「跑步」——具体是什么类型？",
      "answer": "跑步"
    }
  ],
  "draft_tags": {                          // 规则引擎产出
    "personality": [
      {"label": "安静型", "source": "rule", "confidence": 0.9}
    ],
    "hobby": [
      {"label": "跑步", "source": "rule", "confidence": 0.9},
      {"label": "烹饪", "source": "rule", "confidence": 0.8}
    ],
    "lifestyle": [
      {"label": "不吸烟", "source": "rule", "confidence": 0.95}
    ]
  },
  "dimension_gaps": [                       // 规则引擎产出的维度缺口
    {"dimension": "cleaning_habit", "reason": "find_roommate 需求下 cleaning_habit 缺失"},
    {"dimension": "wuzing", "reason": "可从出生年份 1998 推断五行=土"}
  ]
}

Response:
{
  "tags": {
    "personality": [
      {"label": "安静型", "source": "free_text", "confidence": 0.9},
      {"label": "INFP", "source": "free_text", "confidence": 0.85}
    ],
    "hobby": [
      {"label": "跑步", "source": "question_answer", "confidence": 1.0},
      {"label": "烹饪", "source": "free_text", "confidence": 0.85}
    ],
    "lifestyle": [
      {"label": "不吸烟", "source": "free_text", "confidence": 0.95},
      {"label": "宅家型", "source": "free_text", "confidence": 0.75}
    ],
    "roommate_expectation": [
      {"label": "作息规律", "source": "free_text", "confidence": 0.85}
    ],
    "rental_preference": [],
    "wuzing": [
      {"label": "土", "source": "rule", "confidence": 1.0}
    ]
  },
  "questions": [
    {
      "id": "q_new_001",
      "text": "💡 说到安静——你对室友晚上的声音有什么期望？",
      "dimension": "noise_tolerance",
      "strategy": "scenario",
      "options": [
        {"label": "晚上10点以后尽量安静就好", "tag": "室友期望-安静偏好"},
        {"label": "只要不吵到我睡觉就行", "tag": "室友期望-中等噪音容忍"},
        {"label": "不太在意，自由就好", "tag": "室友期望-高噪音容忍"},
        {"label": "✏️ 自己写", "tag": null}
      ]
    },
    {
      "id": "q_new_002",
      "text": "💡 你对合租的清洁标准大概是？",
      "dimension": "cleaning_habit",
      "strategy": "supplement",
      "options": [
        {"label": "定期大扫除，公共区域保持干净", "tag": "室友期望-高清洁标准"},
        {"label": "保持基本整洁，不会太计较", "tag": "室友期望-中等清洁标准"},
        {"label": "随性就好，住得舒服最重要", "tag": "室友期望-低清洁标准"},
        {"label": "✏️ 自己写", "tag": null}
      ]
    }
  ]
}
```

### 4.4 POST /api/profile/ai/bio

```
Request:
{
  "free_text": "我是在上海工作的设计师...",
  "confirmed_tags": {
    "personality": ["安静型", "INFP"],
    "hobby": ["跑步", "烹饪"],
    "lifestyle": ["不吸烟", "宅家型"],
    "roommate_expectation": ["作息规律"],
    "wuzing": ["土"]
  },
  "demand_types": ["find_roommate", "rent"]
}

Response:
{
  "bio": "在上海做设计的INFP，平时比较安静但熟了话不少。工作日规律作息，周末喜欢跑步和做饭——红烧排骨是拿手菜。希望能找到作息规律、不吸烟的室友，偶尔一起下厨就更好了。目前也在找静安区附近的房子。"
}
```

### 4.5 GET /api/profile/tags/taxonomy

```
Response:
{
  "version": "1.0",
  "categories": {
    "personality": {
      "label": "性格标签",
      "icon": "🧠",
      "tags": ["安静型", "外向型", "INFP", "ENFJ", ...]
    },
    "hobby": {
      "label": "爱好标签",
      "icon": "🎯",
      "tags": ["跑步", "健身", "烹饪", "阅读", "音乐", ...]
    },
    "lifestyle": {
      "label": "生活习惯",
      "icon": "🏠",
      "tags": ["早睡型", "晚睡型", "不吸烟", "养宠物", ...]
    },
    "roommate_expectation": {
      "label": "室友期望",
      "icon": "🤝",
      "tags": ["作息规律", "安静", "不吸烟", "偶尔一起做饭", ...]
    },
    "rental_preference": {
      "label": "求租偏好",
      "icon": "🔍",
      "tags": ["静安区", "徐汇区", "一居室", "4000以内", ...]
    },
    "listing_feature": {
      "label": "房源特征",
      "icon": "🏡",
      "tags": ["精装修", "采光好", "地铁口", ...]
    },
    "wuzing": {
      "label": "五行",
      "icon": "☯️",
      "tags": ["金", "木", "水", "火", "土"]
    }
  }
}
```

### 4.6 PUT /api/profile/fields

```
Request:
{
  "basic_fields": {
    "avatar_url": "https://...",
    "nickname": "小王",
    "birth_year": 1998,
    "occupation": "设计师",
    "region": "上海",
    "languages": ["中文", "English"],
    "demand_types": ["find_roommate", "rent"]
  },
  "tags": {
    "personality": ["安静型", "INFP"],
    "hobby": ["跑步", "烹饪"],
    "lifestyle": ["不吸烟", "宅家型"],
    "roommate_expectation": ["作息规律"],
    "rental_preference": ["静安区", "4000以内"],
    "wuzing": ["土"]
  },
  "bio": "在上海做设计的INFP..."
}

Response:
{
  "success": true,
  "profile_id": "p_xxx",
  "tag_count": 8,
  "completeness_score": 92
}
```

---

## 五、AI Prompt 设计

### 5.1 Prompt 结构设计原则

每个 Prompt 由三部分组成：

```
┌──────────────────────┐
│ 系统上下文（可缓存）   │  ← Wellcee 平台背景 + 租房场景 + 用户画像
│ ~200 Token           │    所有 Prompt 共享，支持 Prompt Cache
├──────────────────────┤
│ 任务指令（可缓存）     │  ← 角色定义 + 约束 + 输出格式
│ ~300-400 Token       │    各 Prompt 独立
├──────────────────────┤
│ 动态数据（不可缓存）   │  ← 用户文本 + 需求类型 + 草稿标签
│ ~200-300 Token       │    每次不同
└──────────────────────┘
```

### 5.2 系统上下文块（所有 Prompt 注入）

```
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

### 5.3 追问+标签分析 Prompt（Qwen-Plus 调用）

```
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
- 每个标签必须标注 source（free_text/question_answer）和 confidence（0-1）
- MBTI：用户提到具体类型 → 提取。没提到 → 不提取，不推断
- 标签总数不超过 20 个
- 每次最多生成 3 条追问
- 每条追问必须附带 2-4 个可点击选项 + 1 个「自己写」
- 追问必须与租房/室友场景相关

## 追问策略
- 具象化：检测到模糊标签 → 追问具体（「运动」→ 什么类型？）
- 场景化：检测到可展开的生活习惯 → 追问合租场景
- 画像补充：需求类型下的关键匹配维度缺失 → 主动提示

## 输入
- 用户自由文本：{{free_text}}
- 需求类型：{{demand_types}}
- 规则草稿标签：{{draft_tags}}
- 维度缺口：{{dimension_gaps}}

## 输出格式（严格 JSON）
{
  "tags": {
    "personality": [
      {"label": "标签名", "source": "free_text|question_answer", "confidence": 0.85}
    ],
    "hobby": [...],
    "lifestyle": [...],
    "roommate_expectation": [...],
    "rental_preference": [...],
    "listing_feature": [...],
    "transfer_reason": [...],
    "wuzing": [...]
  },
  "questions": [
    {
      "id": "q_随机6位",
      "text": "💡 追问文本",
      "dimension": "维度名",
      "strategy": "concretize|scenario|supplement",
      "options": [
        {"label": "选项", "tag": "标签全路径"}
      ]
    }
  ]
}
```

### 5.4 简介生成 Prompt（DeepSeek-V3 调用）

```
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
- 用户原文：{{free_text}}
- 已确认标签：{{confirmed_tags}}
- 需求类型：{{demand_types}}

## 结构
- 第一句：我是谁（职业+城市+核心性格）
- 中间：从标签中选 2-3 个最有区分度的点展开
- 收尾：根据需求类型调整
  - 找室友 → 期待什么样的室友
  - 求租 → 正在找什么样的房子
  - 出租/转租 → 房子亮点
  - 暂无需求 → 自然收束

## 输出格式
{"bio": "生成的简介文本"}
```

---

## 六、标签体系数据结构

### 6.1 tag-taxonomy.yaml 结构

```yaml
version: "1.0"
categories:
  personality:
    label: "性格标签"
    icon: "🧠"
    description: "描述性格和社交倾向的标签"
    tags:
      - id: personality-quiet
        label: "安静型"
        keywords: ["安静", "话少", "内向", "独处", "喜静", "不太说话"]
        roommate_relevance: high
      - id: personality-outgoing
        label: "外向型"
        keywords: ["外向", "开朗", "社交", "话多", "喜欢交朋友"]
        roommate_relevance: high
      # ...

  hobby:
    label: "爱好标签"
    icon: "🎯"
    tags:
      - id: hobby-running
        label: "跑步"
        keywords: ["跑步", "慢跑", "夜跑", "晨跑", "马拉松", "jogging"]
        roommate_relevance: medium
      # ...

  lifestyle:
    label: "生活习惯"
    icon: "🏠"
    tags:
      - id: lifestyle-non-smoker
        label: "不吸烟"
        keywords: ["不吸烟", "不抽烟", "禁烟", "无烟", "non-smoker"]
        roommate_relevance: high
        conflicts: ["lifestyle-smoker"]
      # ...

  # ... roommate_expectation, rental_preference, listing_feature, wuzing

mutual_exclusion_rules:
  - group: [lifestyle-smoker, lifestyle-non-smoker]
    rule: "互斥，取 confidence 高者"
  - group: [personality-quiet, personality-outgoing]
    rule: "可共存（介于中间），不冲突"
  # ...

wuzing_rules:
  birth_year_endings:
    0_1: "金"
    2_3: "水"
    4_5: "木"
    6_7: "火"
    8_9: "土"
```

### 6.2 规则引擎关键词匹配逻辑

```python
def extract_exact_tags(free_text: str, taxonomy: dict) -> list[dict]:
    """
    精确关键词匹配提取标签。
    只追求高精度，不追求高召回。
    没匹配到的留给 LLM。
    """
    tags = []
    for category in taxonomy["categories"].values():
        for tag_def in category["tags"]:
            for keyword in tag_def["keywords"]:
                if keyword in free_text:
                    tags.append({
                        "label": tag_def["label"],
                        "category": category["label"],
                        "source": "rule",
                        "confidence": 0.9  # 精确匹配默认高置信度
                    })
                    break  # 一个标签只添加一次
    return tags
```

---

## 七、错误处理与降级

### 7.1 LLM 调用层

```
调用 Qwen-Plus
    ├─ 成功 (2xx) → 校验 JSON Schema
    │   ├─ 校验通过 → 返回
    │   └─ 校验失败 → 重试 1 次
    │       ├─ 重试成功 → 返回
    │       └─ 重试失败 → 切换 GLM-4-Air
    │
    ├─ 超时 (>5s) → 重试 1 次
    │   ├─ 重试成功 → 返回
    │   └─ 重试超时 → 切换 GLM-4-Air
    │
    ├─ 服务端错误 (5xx) → 切换 GLM-4-Air
    └─ 限流 (429) → 等待 1s 后重试，最多 3 次
```

### 7.2 前端错误展示

| 错误类型 | 用户提示 | 用户操作 |
|---------|---------|---------|
| AI 追问超时 | 「AI 暂时有点忙，你可以继续写或者稍后再试」 | 继续编辑 / 重试 |
| 标签提取失败 | 「标签提取暂时不可用，你可以手动选择标签」 | 展示手动标签选择界面 |
| 简介生成失败 | 「简介生成暂时不可用，已为你保存原始文本」 | 直接展示原文作为简介 |

### 7.3 响应 JSON Schema 校验

所有 LLM 返回的 JSON 必须经过后端 Schema 校验，确保前端不会因格式异常而崩溃：

```python
# 校验示例
ANALYZE_RESPONSE_SCHEMA = {
    "type": "object",
    "required": ["tags", "questions"],
    "properties": {
        "tags": {
            "type": "object",
            "properties": {
                "personality": {"type": "array", "maxItems": 10},
                "hobby": {"type": "array", "maxItems": 10},
                # ...
            }
        },
        "questions": {
            "type": "array",
            "maxItems": 3,
            "items": {
                "type": "object",
                "required": ["id", "text", "options"],
                # ...
            }
        }
    }
}
```

---

## 八、向量服务部署方案（BGE-M3）

### 8.1 推荐方案：TEI Docker 部署

```bash
# GPU 部署
docker run --gpus all -p 8080:80 \
  -v $PWD/models:/data \
  ghcr.io/huggingface/text-embeddings-inference:latest \
  --model-id BAAI/bge-m3 \
  --max-batch-tokens 8192

# CPU 部署（开发环境可用）
docker run -p 8080:80 \
  ghcr.io/huggingface/text-embeddings-inference:cpu-latest \
  --model-id BAAI/bge-m3
```

### 8.2 硬件需求

| 环境 | GPU | 内存 |
|------|-----|------|
| 开发 | 无（CPU） | 8GB |
| 生产（< 1000 标签） | RTX 3060+ | 16GB |
| 生产（标签 > 5000） | A10 / A100 | 32GB |

本项目的标签总数 < 1000 个，向量库极小，RTX 3060 完全够用。

### 8.3 索引构建

```python
# 将所有标签文本预计算为向量，存入轻量向量库
import numpy as np

tag_vectors = {}  # {tag_id: np.array(1024,)}
for category in taxonomy["categories"].values():
    for tag_def in category["tags"]:
        embedding = tei_client.encode(tag_def["label"] + ": " + tag_def["description"])
        tag_vectors[tag_def["id"]] = embedding

# 查询时
def find_top_k_tags(text_fragment: str, k: int = 3) -> list[tuple[str, float]]:
    query_vec = tei_client.encode(text_fragment)
    scores = [(tag_id, cosine_similarity(query_vec, vec)) for tag_id, vec in tag_vectors.items()]
    scores.sort(key=lambda x: x[1], reverse=True)
    return scores[:k]
```

---

## 九、监控与运维

### 9.1 关键监控指标

| 指标 | 采集方式 | 告警阈值 |
|------|---------|---------|
| LLM API 延迟（P95） | 后端埋点 | > 5s |
| LLM API 错误率 | 后端埋点 | > 5% |
| JSON Schema 校验失败率 | 后端统计 | > 10% |
| 降级链触发次数 | 计数器 | > 100/小时 |
| Token 消耗量 | API 日志 | > 预算 80% |
| 用户追问采纳率 | 前端埋点 | < 30%（需求调整信号） |

### 9.2 Prompt 版本管理

```
prompts/
├── system_context_v1.txt        # 系统上下文块
├── analyze_v1.txt               # 追问+标签 Prompt
├── bio_v1.txt                   # 简介生成 Prompt
└── changelog.md                 # 变更记录
```

每次修改 Prompt 后，在 `changelog.md` 记录变更内容、原因、预期效果。保留历史版本文件，支持快速回滚。

---

## 十、技术依赖

| 依赖 | 版本/规格 | 用途 |
|------|---------|------|
| Qwen-Plus API | 阿里云百炼 | 追问+标签分析 |
| DeepSeek-V3 API | DeepSeek Platform | 简介生成 |
| BGE-M3 | BAAI / TEI | 标签向量检索 |
| Python | 3.11+ | 后端开发语言 |
| FastAPI | 最新稳定版 | API 框架 |
| Redis | 7.x | Prompt Cache 会话存储 |
| PostgreSQL | 15+ | 用户资料持久化 |
