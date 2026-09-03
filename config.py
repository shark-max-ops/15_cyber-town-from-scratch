"""项目配置读取模块。

主要变量含义：
- api_key：大语言模型API密钥。
- base_url：大语言模型API接口地址。
- model：调用的大语言模型名称。
- config：保存全部配置项的字典。
- missing_items：没有填写的配置项名称列表。
- missing_text：将缺失配置名称拼接成的提示文字。

环境变量含义：
- LLM_API_KEY：DeepSeek API密钥。
- LLM_BASE_URL：DeepSeek API地址。
- LLM_MODEL：DeepSeek模型名称。
"""

import os

from dotenv import load_dotenv


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