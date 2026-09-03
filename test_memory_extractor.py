"""
记忆提取器临时测试程序。

主要变量含义：
- api_key：DeepSeek API密钥。
- base_url：DeepSeek API地址。
- model：DeepSeek模型名称。
- client：DeepSeek API客户端。
- extractor：长期记忆提取器。
- user_message：用于测试的玩家消息。
- result：结构化记忆提取结果。
"""

from openai import OpenAI

# 导入配置读取功能
from config import load_config

# 导入记忆提取器
from memory_extractor import MemoryExtractor


def main() -> None:
    """测试一条玩家消息的记忆提取结果。"""

    # 读取DeepSeek配置
    api_key, base_url, model = load_config()

    # 创建独立API客户端
    client = OpenAI(
        api_key=api_key,
        base_url=base_url,
    )

    # 创建记忆提取器
    extractor = MemoryExtractor(
        client=client,
        model=model,
    )

    # 获取测试消息
    user_message = input(
        "请输入测试消息："
    ).strip()

    # 调用DeepSeek提取记忆
    result = extractor.extract(
        user_message=user_message
    )

    # 转成格式化JSON并显示
    print(
        result.model_dump_json(
            indent=2
        )
    )


# 直接运行本文件时启动测试
if __name__ == "__main__":
    main()
