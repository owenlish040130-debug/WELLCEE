"""
Wellcee 个人资料 AI 增强 — 应用配置
从环境变量 + .env 文件加载，支持本地开发无缝切换
"""
from pathlib import Path
from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

# 显式加载 .env（pydantic-settings v2 需要明确路径）
ENV_PATH = Path(__file__).parent.parent / ".env"
load_dotenv(ENV_PATH)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(ENV_PATH), env_file_encoding="utf-8")

    # 数据库（默认 SQLite，本地零配置）
    database_url: str = "sqlite+aiosqlite:///./wellcee.db"

    # LLM API Keys（至少配一个）
    qwen_api_key: str = ""
    qwen_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"

    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com/v1"

    glm_api_key: str = ""
    glm_base_url: str = "https://open.bigmodel.cn/api/paas/v4"

    # 阿里云 DashScope（语音识别 + Qwen 备选）
    dashscope_api_key: str = ""

    # LLM 调用参数
    llm_timeout: int = 30
    llm_max_retries: int = 2
    max_question_rounds: int = 5

    # Prompt 目录
    prompts_dir: Path = Path(__file__).parent.parent / "prompts"

    # 数据目录
    data_dir: Path = Path(__file__).parent.parent / "data"


settings = Settings()
