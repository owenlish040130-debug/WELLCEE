"""
Prompt 模板引擎。
Prompt 结构：系统上下文（可缓存）+ 任务指令 + 动态数据。
"""
import json
from pathlib import Path
from functools import lru_cache
from app.config import settings


@lru_cache(maxsize=1)
def get_system_context() -> str:
    """加载系统上下文块（所有 Prompt 共享，支持 Prompt Cache）"""
    path = settings.prompts_dir / "system_context.txt"
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()


def render_prompt(template_name: str, variables: dict) -> str:
    """
    渲染 Prompt 模板。

    Args:
        template_name: 'analyze' | 'bio'
        variables: 模板变量字典，值可以是 str / list / dict

    Returns:
        渲染后的完整 Prompt 文本
    """
    path = settings.prompts_dir / f"{template_name}.txt"
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
