"""
项目配置读取模块。

功能说明：
- 从.env文件读取大模型配置。
- 定义项目公共路径。
- 定义Qdrant本地数据库配置。

主要变量含义：
- PROJECT_ROOT：Python后端项目根目录。
- QDRANT_PATH：Qdrant本地数据库目录。
- QDRANT_COLLECTION_NAME：Qdrant长期记忆集合名称。
- api_key：大模型API密钥。
- base_url：大模型API地址。
- model：大模型名称。
"""

import os
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent
QDRANT_PATH = PROJECT_ROOT / "data" / "qdrant"
QDRANT_COLLECTION_NAME = "cyber_town_memories"

def load_config() -> tuple[str, str, str]:
    """读取并检查大语言模型配置。"""

    # 从项目的.env文件加载环境变量
    load_dotenv()

    # 读取DeepSeek API配置
    api_key = os.getenv("LLM_API_KEY")
    base_url = os.getenv("LLM_BASE_URL")
    model = os.getenv("LLM_MODEL")

    # 将配置整理成字典，方便统一检查
    config = {
        "LLM_API_KEY": api_key,
        "LLM_BASE_URL": base_url,
        "LLM_MODEL": model,
    }

    # 找出没有配置或者内容为空的项目
    missing_items = [
        name
        for name, value in config.items()
        if not value
    ]

    # 如果存在缺失配置，立即停止程序并提示
    if missing_items:
        missing_text = ", ".join(missing_items)

        raise ValueError(
            f"缺少环境变量：{missing_text}"
        )

    # 前面已经检查过None，因此这里可以安全返回字符串
    return api_key, base_url, model