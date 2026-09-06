"""
赛博小镇终端程序入口模块。

功能说明：
- 初始化赛博小镇公共应用组件。
- 显示NPC菜单、背景状态和玩家好感度。
- 允许玩家通过终端选择NPC并持续对话。
- 复用DialogueService处理完整对话流程。
- 复用FastAPI版本相同的Qdrant长期记忆系统。
- 在程序退出时安全关闭Qdrant和LLM客户端。

主要变量含义：
- application_context：全部核心组件的统一容器。
- dialogue_service：负责处理单轮NPC对话的业务服务。
- player_id：当前终端玩家的唯一编号。
- npc_id：当前选中的NPC编号。
- background_result：批量生成的NPC背景状态。
- cached_record：从本地读取的背景状态缓存。
- force_refresh：是否忽略缓存并重新生成背景状态。
- memory_archive：NPC保存的完整原始对话档案。
- conversation_history：NPC最近几轮工作记忆。
- qdrant_memories：当前NPC在Qdrant中的长期记忆。
- dialogue_result：DialogueService返回的单轮对话结果。
"""

from application_context import (
    ApplicationContext,
    application_context,
)
from background_models import (
    BatchBackgroundDialogueResult,
)
from dialogue_service import (
    DialogueService,
    NPCBusyError,
    NPCNotFoundError,
)
from memory import (
    get_working_memory,
    load_memory,
)
from npc import NPC
from scene_context import build_scene_context


# 当前终端版本使用固定玩家编号。
#
# Godot客户端目前也使用该编号，
# 因此两个入口可以共享同一份长期记忆和好感度。
DEFAULT_PLAYER_ID = "default_player"


def get_or_generate_background_dialogues(
    context: ApplicationContext,
    force_refresh: bool = False,
) -> BatchBackgroundDialogueResult | None:
    """读取背景缓存，或生成全部NPC的新背景状态。"""

    # 从公共组件容器获取背景缓存。
    background_cache = context.background_cache

    # 读取当前缓存，即使已经过期也暂时保留引用。
    #
    # 如果后面的DeepSeek生成失败，
    # 仍然可以继续使用旧缓存。
    cached_record = background_cache.load()

    if not force_refresh:
        # 只读取仍在有效期内的缓存。
        valid_record = (
            background_cache.load_valid()
        )

        if valid_record is not None:
            remaining_seconds = (
                background_cache
                .get_remaining_seconds(
                    cache_record=valid_record,
                )
            )

            print(
                f"\n[已读取背景对话缓存，"
                f"剩余{remaining_seconds}秒]"
            )

            # 将缓存中的背景动作、情绪和台词
            # 同步到NPC运行状态管理器。
            context.state_manager.update_background_states(
                background_result=(
                    valid_record.result
                ),
            )

            return valid_record.result

    if force_refresh:
        print(
            "\n正在强制刷新所有NPC背景状态……"
        )
    else:
        print(
            "\n背景对话缓存不存在或已过期。"
        )
        print(
            "正在批量生成所有NPC背景状态……"
        )

    # 根据当前时间构造小镇场景。
    scene_context = build_scene_context(
        weather="天气晴朗，微风轻柔",
        special_event=None,
    )

    try:
        # 一次DeepSeek调用生成全部NPC的背景状态。
        background_result = (
            context
            .batch_dialogue_generator
            .generate(
                npcs=(
                    context
                    .npc_manager
                    .get_all_npcs()
                ),
                scene_context=scene_context,
            )
        )

        # 保存背景状态缓存。
        background_cache.save(
            scene_context=scene_context,
            result=background_result,
        )

        # 把新背景状态同步到StateManager。
        context.state_manager.update_background_states(
            background_result=background_result,
        )

        print("NPC背景状态批量生成成功。")
        print(
            f"[场景："
            f"{background_result.scene_summary}]"
        )

        return background_result

    except Exception as error:
        # 背景状态属于附加功能，
        # 生成失败不应该影响NPC正常对话。
        print(
            f"[NPC背景状态生成失败：{error}]"
        )

        # 存在旧缓存时继续使用旧内容。
        if cached_record is not None:
            print(
                "[继续使用之前的背景状态缓存]"
            )

            context.state_manager.update_background_states(
                background_result=(
                    cached_record.result
                ),
            )

            return cached_record.result

        return None


def show_npc_menu(
    context: ApplicationContext,
    background_result: (
        BatchBackgroundDialogueResult | None
    ),
    player_id: str,
) -> list[NPC]:
    """显示NPC列表、背景状态和好感度。"""

    npcs = context.npc_manager.get_all_npcs()

    # 建立npc_id到背景状态的快速映射。
    background_map = {}

    if background_result is not None:
        background_map = {
            dialogue.npc_id: dialogue
            for dialogue
            in background_result.dialogues
        }

    print("\n========== 赛博小镇 ==========")

    if background_result is not None:
        print(
            f"当前场景："
            f"{background_result.scene_summary}"
        )

    print("\n请选择要交谈的NPC：")

    for index, npc in enumerate(
        npcs,
        start=1,
    ):
        # 查询当前玩家和NPC的关系。
        relationship = (
            context
            .relationship_manager
            .get_relationship(
                npc_id=npc.npc_id,
                player_id=player_id,
            )
        )

        print(
            f"\n{index}. "
            f"{npc.name}——{npc.role}"
        )

        print(
            f"   关系：{relationship.level}"
            f"（{relationship.score}/100）"
        )

        print(
            f"   互动："
            f"{relationship.interaction_count}次"
        )

        background_dialogue = (
            background_map.get(npc.npc_id)
        )

        if background_dialogue is not None:
            print(
                f"   动作："
                f"{background_dialogue.action}"
            )
            print(
                f"   情绪："
                f"{background_dialogue.emotion}"
            )
            print(
                f"   台词："
                f"“{background_dialogue.speech}”"
            )
        else:
            print(
                "   状态：正在进行日常活动"
            )

    print("\nr. 刷新所有NPC背景状态")
    print("0. 退出程序")
    print("==============================")

    return npcs


def run_chat(
    *,
    context: ApplicationContext,
    dialogue_service: DialogueService,
    npc: NPC,
    player_id: str,
) -> None:
    """运行玩家与指定NPC之间的持续对话。"""

    npc_id = npc.npc_id

    # 原始对话档案仍然保存在JSON中。
    memory_archive = load_memory(
        npc_id=npc_id,
    )

    conversation_history = get_working_memory(
        memory_archive=memory_archive,
    )

    # 长期记忆直接从Qdrant读取，
    # 不再加载*_vector_memory.json。
    qdrant_memories = (
        context
        .qdrant_store
        .list_memories(
            npc_id=npc_id,
            player_id=player_id,
        )
    )

    relationship = (
        context
        .relationship_manager
        .get_relationship(
            npc_id=npc_id,
            player_id=player_id,
        )
    )

    print(
        f"\n已保存{len(memory_archive) // 2}轮历史，"
        f"本次工作记忆"
        f"{len(conversation_history) // 2}轮，"
        f"Qdrant长期记忆"
        f"{len(qdrant_memories)}条。"
    )

    print(
        f"[当前关系：{relationship.level}；"
        f"好感度：{relationship.score}/100；"
        f"互动次数："
        f"{relationship.interaction_count}]"
    )

    print("输入“返回”可以选择其他NPC。")
    print("输入“退出”可以结束程序。")

    while True:
        player_message = input(
            "\n你："
        ).strip()

        if player_message in {
            "退出",
            "exit",
            "quit",
        }:
            print("对话结束。")
            raise SystemExit

        if player_message in {
            "返回",
            "back",
        }:
            print(
                f"你结束了与{npc.name}的对话。"
            )
            return

        if not player_message:
            print(
                "输入不能为空，请重新输入。"
            )
            continue

        print(f"{npc.name}正在思考……")

        try:
            # DialogueService统一执行：
            #
            # NPC状态占用；
            # Qdrant长期记忆检索；
            # NPC回复生成；
            # 好感度更新；
            # 原始档案保存；
            # Qdrant长期记忆提取；
            # JSON备份；
            # 对话日志。
            dialogue_result = (
                dialogue_service
                .process_dialogue(
                    npc_id=npc_id,
                    player_id=player_id,
                    player_message=(
                        player_message
                    ),
                )
            )

        except NPCNotFoundError as error:
            print(f"[NPC不存在：{error}]")
            return

        except NPCBusyError as error:
            print(f"[NPC正忙：{error}]")
            continue

        except Exception as error:
            print(
                f"[NPC对话处理失败：{error}]"
            )
            continue

        print(
            f"\n{dialogue_result.npc_name}："
            f"{dialogue_result.npc_reply}"
        )

        if dialogue_result.affinity_change > 0:
            change_text = (
                f"+{dialogue_result.affinity_change}"
            )
        else:
            change_text = str(
                dialogue_result.affinity_change
            )

        print(
            f"[好感度变化：{change_text}；"
            f"当前关系："
            f"{dialogue_result.affinity_level}；"
            f"当前分数："
            f"{dialogue_result.affinity_score}/100]"
        )

        print(
            f"[本轮使用长期记忆："
            f"{dialogue_result.retrieved_memory_count}条]"
        )

        # 从Qdrant重新统计当前NPC长期记忆。
        qdrant_memories = (
            context
            .qdrant_store
            .list_memories(
                npc_id=npc_id,
                player_id=player_id,
            )
        )

        print(
            f"[Qdrant长期记忆："
            f"{len(qdrant_memories)}条]"
        )


def run_town(
    *,
    context: ApplicationContext,
    dialogue_service: DialogueService,
    player_id: str,
) -> None:
    """运行赛博小镇终端菜单。"""

    force_refresh = False

    while True:
        background_result = (
            get_or_generate_background_dialogues(
                context=context,
                force_refresh=force_refresh,
            )
        )

        # 当前刷新请求已经处理完成。
        force_refresh = False

        npcs = show_npc_menu(
            context=context,
            background_result=background_result,
            player_id=player_id,
        )

        choice = input(
            "\n请输入NPC编号："
        ).strip()

        if (
            choice.lower() == "r"
            or choice == "刷新"
        ):
            force_refresh = True
            continue

        if choice in {
            "0",
            "退出",
            "exit",
            "quit",
        }:
            print("你离开了赛博小镇。")
            return

        if not choice.isdigit():
            print(
                "请输入正确的NPC编号。"
            )
            continue

        npc_index = int(choice) - 1

        if (
            npc_index < 0
            or npc_index >= len(npcs)
        ):
            print(
                "没有这个NPC，请重新选择。"
            )
            continue

        selected_npc = npcs[npc_index]

        print(
            f"\n你来到了"
            f"{selected_npc.name}面前。"
        )
        print(
            f"{selected_npc.name}的身份："
            f"{selected_npc.role}"
        )

        # NPC状态占用已经由DialogueService处理，
        # 这里不再重复调用StateManager。
        run_chat(
            context=context,
            dialogue_service=dialogue_service,
            npc=selected_npc,
            player_id=player_id,
        )


def main() -> None:
    """初始化公共组件并启动终端小镇。"""

    try:
        # 终端版和FastAPI版使用相同组件初始化流程。
        application_context.initialize()

        # DialogueService只是保存公共组件引用，
        # 不会重复创建Embedding或Qdrant。
        dialogue_service = DialogueService(
            context=application_context,
        )

        run_town(
            context=application_context,
            dialogue_service=dialogue_service,
            player_id=DEFAULT_PLAYER_ID,
        )

    finally:
        # 正常退出、SystemExit或者异常退出时，
        # 都要释放Qdrant本地数据库文件锁。
        application_context.shutdown()


if __name__ == "__main__":
    main()