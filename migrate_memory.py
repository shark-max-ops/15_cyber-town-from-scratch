"""
migrate_memory.py

旧对话档案迁移工具，负责：

1. 扫描data目录中的NPC原始对话档案；
2. 提取其中所有玩家消息；
3. 调用DeepSeek分析长期记忆；
4. 转换成新版StoredMemory结构；
5. 生成Embedding并写入新版向量记忆文件。

这个文件只需要在记忆结构升级后运行一次。
"""

from pathlib import Path

from openai import OpenAI
from sentence_transformers import SentenceTransformer

from config import load_config
from memory import (
    apply_memory_extraction,
    load_memory,
    load_vector_memory,
)
from memory_extractor import MemoryExtractor


# 项目根目录：
# migrate_memory.py所在的文件夹。
PROJECT_ROOT = Path(__file__).resolve().parent

# 数据目录：
# 保存NPC原始对话档案和向量记忆。
DATA_DIR = PROJECT_ROOT / "data"

# Embedding模型名称：
# 必须与main.py使用相同的模型。
EMBEDDING_MODEL_NAME = "BAAI/bge-small-zh-v1.5"


def create_llm_client(
    api_key: str,
    base_url: str,
) -> OpenAI:
    """创建DeepSeek兼容客户端。"""

    # DeepSeek使用OpenAI兼容API。
    return OpenAI(
        api_key=api_key,
        base_url=base_url,
    )


def discover_npc_ids() -> list[str]:
    """从data目录中找出拥有原始对话档案的NPC。"""

    # data目录不存在时，没有可以迁移的数据。
    if not DATA_DIR.exists():
        return []

    npc_ids: list[str] = []

    # 原始档案的文件名格式为：
    # lin_zhou_memory.json
    for memory_file in DATA_DIR.glob("*_memory.json"):
        # 排除向量记忆文件：
        # lin_zhou_vector_memory.json
        if memory_file.name.endswith("_vector_memory.json"):
            continue

        # 去掉文件名末尾的_memory.json，
        # 得到NPC ID。
        npc_id = memory_file.name.removesuffix(
            "_memory.json"
        )

        npc_ids.append(npc_id)

    # 排序可以让每次迁移的处理顺序保持一致。
    return sorted(npc_ids)


def migrate_npc_memory(
    npc_id: str,
    embedding_model: SentenceTransformer,
    memory_extractor: MemoryExtractor,
) -> None:
    """迁移一个NPC的全部玩家历史消息。"""

    # 加载该NPC的完整原始对话档案。
    memory_archive = load_memory(
        npc_id=npc_id,
    )

    # 加载当前已有的新版结构化记忆。
    #
    # 不符合StoredMemory格式的旧记忆会被memory.py忽略。
    vector_memories = load_vector_memory(
        npc_id=npc_id,
    )

    # 只处理玩家消息。
    #
    # NPC回复可能包含模型编造的信息，
    # 因此不能把NPC回复当成可靠长期记忆。
    user_messages = [
        message.get("content", "").strip()
        for message in memory_archive
        if (
            message.get("role") == "user"
            and message.get("content", "").strip()
        )
    ]

    print(f"\n开始迁移NPC：{npc_id}")
    print(f"找到{len(user_messages)}条玩家历史消息")

    # 记录整个NPC的迁移统计。
    total_statistics = {
        "added": 0,
        "updated": 0,
        "deleted": 0,
        "skipped": 0,
        "failed": 0,
    }

    # 逐条调用DeepSeek分析玩家历史消息。
    for index, user_message in enumerate(
        user_messages,
        start=1,
    ):
        print(
            f"\n[{npc_id}：{index}/{len(user_messages)}]"
        )
        print(f"玩家消息：{user_message}")

        try:
            # 记忆提取器只接收玩家原始消息，
            # 不接收NPC回复和其他历史。
            extraction_result = memory_extractor.extract(
                user_message=user_message,
            )

            # 应用REMEMBER、FORGET或NONE操作。
            statistics = apply_memory_extraction(
                npc_id=npc_id,
                vector_memories=vector_memories,
                extraction_result=extraction_result,
                embedding_model=embedding_model,
            )

            # 累加当前消息的处理结果。
            for statistic_name in (
                "added",
                "updated",
                "deleted",
                "skipped",
            ):
                total_statistics[statistic_name] += (
                    statistics[statistic_name]
                )

            print(
                "处理结果："
                f"新增{statistics['added']}条，"
                f"更新{statistics['updated']}条，"
                f"删除{statistics['deleted']}条，"
                f"跳过{statistics['skipped']}条"
            )

            # 每次处理后重新加载向量记忆。
            #
            # 后续消息需要基于最新记忆判断：
            # 是新增事实，还是更新已有事实。
            vector_memories = load_vector_memory(
                npc_id=npc_id,
            )

        except Exception as error:
            # 某一条消息失败时继续迁移其他消息。
            total_statistics["failed"] += 1
            print(f"迁移失败：{error}")

    # 显示当前NPC的最终迁移结果。
    print(f"\nNPC {npc_id} 迁移完成")
    print(
        f"新增：{total_statistics['added']}条；"
        f"更新：{total_statistics['updated']}条；"
        f"删除：{total_statistics['deleted']}条；"
        f"跳过：{total_statistics['skipped']}条；"
        f"失败：{total_statistics['failed']}条；"
        f"最终记忆：{len(vector_memories)}条"
    )


def main() -> None:
    """执行所有NPC的历史记忆迁移。"""

    # 读取DeepSeek环境配置。
    api_key, base_url, model = load_config()

    print("配置读取成功")
    print(f"当前模型：{model}")

    # 创建DeepSeek客户端。
    client = create_llm_client(
        api_key=api_key,
        base_url=base_url,
    )

    # 加载Embedding模型。
    print(
        f"正在加载Embedding模型："
        f"{EMBEDDING_MODEL_NAME}"
    )

    embedding_model = SentenceTransformer(
        EMBEDDING_MODEL_NAME,
    )

    print("Embedding模型加载成功")

    # 创建长期记忆提取器。
    memory_extractor = MemoryExtractor(
        client=client,
        model=model,
    )

    # 自动寻找所有NPC的原始档案。
    npc_ids = discover_npc_ids()

    if not npc_ids:
        print("没有找到可以迁移的NPC对话档案。")
        return

    print(
        f"发现{len(npc_ids)}个NPC档案："
        f"{', '.join(npc_ids)}"
    )

    # 依次迁移每个NPC。
    for npc_id in npc_ids:
        migrate_npc_memory(
            npc_id=npc_id,
            embedding_model=embedding_model,
            memory_extractor=memory_extractor,
        )

    print("\n全部NPC历史记忆迁移完成。")


# 直接运行本文件时开始迁移。
if __name__ == "__main__":
    main()