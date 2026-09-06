"""
NPC历史对话长期记忆重新提取工具。

功能说明：
- 扫描全部NPC的原始对话档案。
- 只读取玩家消息，不把NPC回复当成可靠事实。
- 重新调用DeepSeek提取结构化长期记忆。
- 使用QdrantMemoryManager执行新增、更新和遗忘。
- 将Qdrant作为正式长期记忆存储。
- 操作成功后自动生成旧版向量JSON备份。

使用场景：
- 长期记忆提取规则发生较大变化；
- memory_key设计得到改进；
- 需要从完整历史中重新构建长期记忆；
- 旧版向量记录无法通过StoredMemory验证。

主要变量含义：
- application_context：全部核心组件的统一容器。
- DEFAULT_PLAYER_ID：旧对话档案对应的默认玩家编号。
- DATA_DIR：原始对话档案所在目录。
- npc_ids：从data目录中发现的全部NPC编号。
- npc_id：当前正在迁移的NPC编号。
- memory_archive：当前NPC的完整原始对话档案。
- user_messages：从档案中提取出的全部玩家消息。
- user_message：当前交给DeepSeek分析的一条玩家消息。
- extraction_result：DeepSeek生成的结构化记忆操作。
- statistics：当前消息的记忆处理统计。
- total_statistics：当前NPC全部历史消息的累计统计。
- qdrant_memories：迁移后保存在Qdrant中的长期记忆。
"""

from pathlib import Path

from application_context import (
    ApplicationContext,
    application_context,
)
from memory import load_memory


# 当前项目尚未实现正式玩家登录，
# 原始对话档案统一归属于默认玩家。
DEFAULT_PLAYER_ID = "default_player"

# 项目根目录。
PROJECT_ROOT = Path(__file__).resolve().parent

# NPC原始对话档案所在目录。
DATA_DIR = PROJECT_ROOT / "data"


def discover_npc_ids() -> list[str]:
    """从原始对话文件中发现全部NPC编号。"""

    if not DATA_DIR.exists():
        return []

    npc_ids: list[str] = []

    # 原始对话文件格式：
    #
    # lin_zhou_memory.json
    # wang_professor_memory.json
    # kang_kang_memory.json
    for memory_file in DATA_DIR.glob(
        "*_memory.json"
    ):
        # 排除结构化向量记忆备份：
        #
        # lin_zhou_vector_memory.json
        if memory_file.name.endswith(
            "_vector_memory.json"
        ):
            continue

        npc_id = memory_file.name.removesuffix(
            "_memory.json"
        )

        if npc_id:
            npc_ids.append(npc_id)

    # 排序保证每次运行的处理顺序一致。
    return sorted(npc_ids)


def migrate_npc_memory(
    *,
    context: ApplicationContext,
    npc_id: str,
    player_id: str,
) -> dict[str, int]:
    """重新提取一个NPC的全部玩家历史消息。"""

    # 加载该NPC的完整原始对话档案。
    memory_archive = load_memory(
        npc_id=npc_id,
    )

    # 只提取玩家自己说过的话。
    #
    # NPC回复可能含有角色扮演内容或模型编造信息，
    # 不能将其当成玩家提供的可靠事实。
    user_messages = [
        str(
            message.get("content", "")
        ).strip()
        for message in memory_archive
        if (
            message.get("role") == "user"
            and str(
                message.get("content", "")
            ).strip()
        )
    ]

    print("-" * 60)
    print(f"开始重新提取NPC记忆：{npc_id}")
    print(
        f"找到{len(user_messages)}条玩家历史消息"
    )

    total_statistics = {
        "added": 0,
        "updated": 0,
        "deleted": 0,
        "skipped": 0,
        "qdrant_written": 0,
        "qdrant_deleted": 0,
        "qdrant_failed": 0,
        "backup_failed": 0,
        "message_failed": 0,
    }

    for index, user_message in enumerate(
        user_messages,
        start=1,
    ):
        print(
            f"\n[{npc_id}："
            f"{index}/{len(user_messages)}]"
        )
        print(f"玩家消息：{user_message}")

        try:
            # 每条历史消息独立交给DeepSeek分析。
            #
            # 不传入NPC回复，防止模型生成内容污染记忆。
            extraction_result = (
                context
                .memory_extractor
                .extract(
                    user_message=user_message,
                )
            )

            # 使用与实时对话完全相同的Qdrant管理器。
            #
            # 管理器会判断ADD、UPDATE、DELETE或SKIP，
            # 并在Qdrant变化后生成JSON备份。
            statistics = (
                context
                .qdrant_memory_manager
                .apply_extraction(
                    npc_id=npc_id,
                    player_id=player_id,
                    extraction_result=(
                        extraction_result
                    ),
                )
            )

            # 累加所有统计项目。
            for statistic_name in (
                "added",
                "updated",
                "deleted",
                "skipped",
                "qdrant_written",
                "qdrant_deleted",
                "qdrant_failed",
                "backup_failed",
            ):
                total_statistics[
                    statistic_name
                ] += statistics[
                    statistic_name
                ]

            print(
                "处理结果："
                f"新增{statistics['added']}条，"
                f"更新{statistics['updated']}条，"
                f"删除{statistics['deleted']}条，"
                f"跳过{statistics['skipped']}条；"
                f"Qdrant写入"
                f"{statistics['qdrant_written']}条，"
                f"Qdrant失败"
                f"{statistics['qdrant_failed']}条"
            )

        except Exception as error:
            # 单条历史消息失败时继续处理后续消息。
            total_statistics[
                "message_failed"
            ] += 1

            print(
                f"[历史消息记忆提取失败："
                f"{error}]"
            )

            # 尝试写入错误日志。
            try:
                context.dialogue_logger.log_error(
                    context=(
                        "重新提取NPC历史长期记忆"
                    ),
                    error=error,
                    npc_id=npc_id,
                    player_id=player_id,
                )

            except Exception as log_error:
                print(
                    f"[错误日志写入失败："
                    f"{log_error}]"
                )

    # 从Qdrant读取最终记忆数量。
    qdrant_memories = (
        context
        .qdrant_store
        .list_memories(
            npc_id=npc_id,
            player_id=player_id,
        )
    )

    print(f"\nNPC {npc_id} 处理完成")
    print(
        f"新增：{total_statistics['added']}条；"
        f"更新：{total_statistics['updated']}条；"
        f"删除：{total_statistics['deleted']}条；"
        f"跳过：{total_statistics['skipped']}条；"
        f"Qdrant写入："
        f"{total_statistics['qdrant_written']}条；"
        f"Qdrant删除："
        f"{total_statistics['qdrant_deleted']}条；"
        f"Qdrant失败："
        f"{total_statistics['qdrant_failed']}条；"
        f"备份失败："
        f"{total_statistics['backup_failed']}条；"
        f"消息失败："
        f"{total_statistics['message_failed']}条；"
        f"最终Qdrant记忆："
        f"{len(qdrant_memories)}条"
    )

    return total_statistics


def main() -> None:
    """重新提取全部NPC的历史长期记忆。"""

    print("=" * 60)
    print("开始重新提取NPC历史长期记忆")
    print("=" * 60)

    try:
        # 复用项目统一初始化流程。
        #
        # 这里会创建DeepSeek客户端、Embedding模型、
        # Qdrant存储器和长期记忆管理器。
        application_context.initialize()

        npc_ids = discover_npc_ids()

        if not npc_ids:
            print(
                "没有找到可以处理的NPC原始对话档案。"
            )
            return

        print(
            f"发现{len(npc_ids)}个NPC档案："
            f"{', '.join(npc_ids)}"
        )

        all_statistics = {
            "added": 0,
            "updated": 0,
            "deleted": 0,
            "skipped": 0,
            "qdrant_written": 0,
            "qdrant_deleted": 0,
            "qdrant_failed": 0,
            "backup_failed": 0,
            "message_failed": 0,
        }

        for npc_id in npc_ids:
            npc_statistics = migrate_npc_memory(
                context=application_context,
                npc_id=npc_id,
                player_id=DEFAULT_PLAYER_ID,
            )

            for statistic_name in all_statistics:
                all_statistics[
                    statistic_name
                ] += npc_statistics[
                    statistic_name
                ]

        print("=" * 60)
        print("全部NPC历史长期记忆处理完成")
        print(
            f"新增：{all_statistics['added']}条；"
            f"更新：{all_statistics['updated']}条；"
            f"删除：{all_statistics['deleted']}条；"
            f"跳过：{all_statistics['skipped']}条；"
            f"Qdrant写入："
            f"{all_statistics['qdrant_written']}条；"
            f"Qdrant失败："
            f"{all_statistics['qdrant_failed']}条；"
            f"备份失败："
            f"{all_statistics['backup_failed']}条；"
            f"消息失败："
            f"{all_statistics['message_failed']}条"
        )
        print("=" * 60)

    finally:
        # 迁移结束后释放Qdrant文件锁和LLM客户端。
        application_context.shutdown()


if __name__ == "__main__":
    main()