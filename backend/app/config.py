"""
Wellcee 个人资料 AI 增强 — 应用配置
从环境变量 + .env 文件加载，支持本地开发无缝切换
"""
from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    # 数据库（默认 SQLite，本地零配置）
    database_url: str = "sqlite+aiosqlite:///./wellcee.db"

    # LLM API Keys（至少配一个）
    qwen_api_key: str = ""
    qwen_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"

    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com/v1"

    glm_api_key: str = ""
    glm_base_url: str = "https://open.bigmodel.cn/api/paas/v4"

    # LLM 调用参数
    llm_timeout: int = 10
    llm_max_retries: int = 1
    max_question_rounds: int = 5

    # Prompt 目录
    prompts_dir: Path = Path(__file__).parent.parent / "prompts"

    # 数据目录
    data_dir: Path = Path(__file__).parent.parent / "data"

    class Config:
        env_file = ".env"


settings = Settings()
