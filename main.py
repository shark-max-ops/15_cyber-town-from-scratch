"""
赛博小镇程序主入口模块。

功能说明：
负责读取配置、初始化NPC、加载记忆系统、生成背景对话、
显示NPC菜单，以及管理玩家与NPC的持续对话。

主要变量含义：
- client：DeepSeek API客户端。
- model：当前使用的大语言模型名称。
- embedding_model：用于长期记忆检索的Embedding模型。
- memory_extractor：长期记忆写入提取器。
- memory_query_planner：长期记忆查询规划器。
- affinity_analyzer：使用DeepSeek分析玩家态度的分析器。
- relationship_manager：负责读取、更新和保存NPC好感度。
- npc_manager：全部NPC对象的统一管理器。
- batch_dialogue_generator：NPC批量背景对话生成器。
- background_cache：NPC背景对话缓存管理器。
- background_result：当前有效的批量背景对话结果。
- scene_context：当前赛博小镇的场景描述。
- relationship：玩家与当前NPC之间的好感度记录。
- relationship_update：本轮对话产生的好感度更新结果。
- player_id：当前玩家唯一编号。
- force_refresh：是否强制忽略缓存并重新生成背景对话。
- cached_record：当前读取到的有效背景对话缓存。
- state_manager：管理全部NPC的运行状态和对话占用。
- interaction_started：当前玩家是否成功占用NPC。
"""

from openai import OpenAI
from sentence_transformers import SentenceTransformer

from affinity_analyzer import AffinityAnalyzer
from agents import NPCAgentManager
from background_cache import BackgroundDialogueCache
from background_models import BatchBackgroundDialogueResult
from batch_dialogue import BatchDialogueGenerator
from config import load_config
from memory import (
    apply_memory_extraction,
    get_working_memory,
    load_memory,
    load_vector_memory,
    retrieve_relevant_memories,
    save_memory,
)
from memory_extractor import MemoryExtractor
from memory_query_planner import MemoryQueryPlanner
from npc import NPC
from relationship_manager import RelationshipManager
from scene_context import build_scene_context
# 导入NPC运行状态管理器。
from state_manager import StateManager

# Embedding模型名称：
# 用于将玩家问题和长期记忆转换成向量。
EMBEDDING_MODEL_NAME = "BAAI/bge-small-zh-v1.5"

# 当前终端版本只有一个玩家。
#
# 后续接入登录系统或Godot后，
# 可以替换成真实玩家账号ID。
DEFAULT_PLAYER_ID = "default_player"


def create_llm_client(
    api_key: str,
    base_url: str,
) -> OpenAI:
    """根据环境配置创建OpenAI兼容客户端。"""

    # DeepSeek提供OpenAI兼容接口，
    # 因此可以直接使用OpenAI客户端。
    client = OpenAI(
        api_key=api_key,
        base_url=base_url,
    )

    return client


def run_chat(
    npc: NPC,
    embedding_model: SentenceTransformer,
    memory_extractor: MemoryExtractor,
    memory_query_planner: MemoryQueryPlanner,
    relationship_manager: RelationshipManager,
    player_id: str = DEFAULT_PLAYER_ID,
) -> None:
    """运行玩家与指定NPC之间的持续对话。"""

    # npc_id用于区分不同NPC的独立记忆文件。
    npc_id = npc.npc_id

    # 加载当前NPC的全部原始对话档案。
    memory_archive = load_memory(
        npc_id=npc_id,
    )

    # 从完整对话档案中提取最近几轮工作记忆。
    conversation_history = get_working_memory(
        memory_archive=memory_archive,
    )

    # 加载当前NPC的结构化长期向量记忆。
    vector_memories = load_vector_memory(
        npc_id=npc_id,
    )

    # 读取玩家与当前NPC之间的好感度。
    relationship = relationship_manager.get_relationship(
        npc_id=npc_id,
        player_id=player_id,
    )

    # 显示当前NPC的记忆状态。
    print(
        f"\n已保存{len(memory_archive) // 2}轮历史，"
        f"本次加载最近{len(conversation_history) // 2}轮，"
        f"长期向量记忆{len(vector_memories)}条。"
    )

    # 显示玩家与当前NPC的关系状态。
    print(
        f"[当前关系：{relationship.level}；"
        f"好感度：{relationship.score}/100；"
        f"互动次数：{relationship.interaction_count}]"
    )

    print("输入“返回”可以选择其他NPC。")
    print("输入“退出”可以结束程序。")

    while True:
        # 读取并清理玩家输入。
        user_message = input("\n你：").strip()

        # “退出”用于结束整个程序。
        if user_message in {
            "退出",
            "exit",
            "quit",
        }:
            print("对话结束。")
            raise SystemExit

        # “返回”只结束当前NPC的对话。
        if user_message in {
            "返回",
            "back",
        }:
            print(f"你结束了与{npc.name}的对话。")
            return

        # 不向模型发送空消息。
        if not user_message:
            print("输入不能为空，请重新输入。")
            continue

        print(f"{npc.name}正在思考……")

        # 第一步：
        # 让DeepSeek判断当前问题是否需要长期记忆，
        # 并生成可能对应的memory_key。
        try:
            query_plan = memory_query_planner.plan(
                user_message=user_message,
            )

            # 显示查询计划，方便学习和调试。
            print(
                "[记忆查询计划："
                f"需要记忆={query_plan.needs_memory}；"
                f"记忆键={query_plan.memory_keys}；"
                f"语义查询="
                f"{query_plan.semantic_query or '无'}；"
                f"置信度={query_plan.confidence:.2f}]"
            )

            # 显示查询规划原因。
            if query_plan.reason:
                print(
                    f"[查询规划原因："
                    f"{query_plan.reason}]"
                )

        except Exception as error:
            # 查询规划失败时退回纯Embedding检索。
            print(f"[记忆查询规划失败：{error}]")
            query_plan = None

        # 第二步：
        # 使用memory_key精确匹配和Embedding语义检索。
        try:
            retrieved_memories = (
                retrieve_relevant_memories(
                    vector_memories=vector_memories,
                    query=user_message,
                    embedding_model=embedding_model,
                    query_plan=query_plan,
                )
            )

        except Exception as error:
            # 长期记忆检索失败时，
            # NPC仍然可以使用工作记忆回复。
            print(f"[长期记忆检索失败：{error}]")
            retrieved_memories = []

        # 显示检索结果。
        print(
            f"[检索到{len(retrieved_memories)}"
            f"条相关长期记忆]"
        )

        # 逐条显示检索到的长期记忆。
        for index, memory in enumerate(
            retrieved_memories,
            start=1,
        ):
            print(f"[长期记忆{index}] {memory}")

        # 第三步：
        # 结合角色设定、记忆和当前好感度生成回复。
        try:
            # 使用更新前的好感度生成本轮回复。
            #
            # 玩家本轮态度产生的好感度变化，
            # 会从下一轮回复开始生效。
            reply = npc.generate_reply(
                conversation_history=conversation_history,
                retrieved_memories=retrieved_memories,
                user_message=user_message,
                affinity_level=relationship.level,
                affinity_score=relationship.score,
            )

        except Exception as error:
            print(f"调用模型失败：{error}")
            continue

        # 输出NPC回复。
        print(f"\n{npc.name}：{reply}")

        # 第四步：
        # NPC成功回复后分析玩家态度并更新好感度。
        try:
            relationship_update = (
                relationship_manager.update_relationship(
                    npc_id=npc_id,
                    player_id=player_id,
                    player_message=user_message,
                )
            )

            # 保存更新后的关系记录。
            relationship = (
                relationship_update.relationship
            )

            # 显示DeepSeek态度分析结果。
            print(
                "[玩家态度分析："
                f"{relationship_update.analysis.attitude}；"
                f"置信度="
                f"{relationship_update.analysis.confidence:.2f}；"
                f"原因="
                f"{relationship_update.analysis.reason}]"
            )

            # 格式化正负好感度变化。
            if relationship_update.applied_change > 0:
                change_text = (
                    f"+{relationship_update.applied_change}"
                )
            else:
                change_text = str(
                    relationship_update.applied_change
                )

            # 显示本轮实际好感度变化。
            print(
                f"[好感度变化：{change_text}；"
                f"当前关系：{relationship.level}；"
                f"当前分数：{relationship.score}/100]"
            )

            # 重复消息不再获得正向分数。
            if relationship_update.duplicate_message:
                print(
                    "[检测到近期重复消息，"
                    "正向好感度已取消]"
                )

        except Exception as error:
            # 好感度更新失败不影响后续记忆保存。
            print(f"[好感度更新失败：{error}]")

        # 第五步：
        # 将本轮玩家消息加入完整原始档案。
        memory_archive.append(
            {
                "role": "user",
                "content": user_message,
            }
        )

        # 将本轮NPC回复加入完整原始档案。
        memory_archive.append(
            {
                "role": "assistant",
                "content": reply,
            }
        )

        # 每轮对话结束后立即保存原始档案。
        try:
            save_memory(
                npc_id=npc_id,
                memory_archive=memory_archive,
            )

        except Exception as error:
            print(
                f"[原始对话档案保存失败：{error}]"
            )

        # 重新提取最近几轮，作为下一轮工作记忆。
        conversation_history = get_working_memory(
            memory_archive=memory_archive,
        )

        # 第六步：
        # 只把本轮玩家原始消息交给长期记忆提取器。
        #
        # 不传入NPC回复，防止模型编造内容污染记忆。
        try:
            extraction_result = memory_extractor.extract(
                user_message=user_message,
            )

            # 应用REMEMBER、FORGET或NONE操作。
            memory_statistics = apply_memory_extraction(
                npc_id=npc_id,
                vector_memories=vector_memories,
                extraction_result=extraction_result,
                embedding_model=embedding_model,
            )

            # 显示长期记忆处理结果。
            print(
                "[长期记忆处理："
                f"新增{memory_statistics['added']}条，"
                f"更新{memory_statistics['updated']}条，"
                f"删除{memory_statistics['deleted']}条，"
                f"跳过{memory_statistics['skipped']}条]"
            )

        except Exception as error:
            # 长期记忆失败不影响正常对话。
            print(f"[长期记忆提取失败：{error}]")

        # 第七步：
        # 重新读取最新的结构化向量记忆。
        try:
            vector_memories = load_vector_memory(
                npc_id=npc_id,
            )

        except Exception as error:
            print(
                f"[长期向量记忆加载失败：{error}]"
            )
            vector_memories = []

        # 显示当前NPC的记忆状态。
        print(
            f"[完整档案：{len(memory_archive) // 2}轮；"
            f"工作记忆：{len(conversation_history) // 2}轮；"
            f"向量记忆：{len(vector_memories)}条]"
        )


def get_or_generate_background_dialogues(
    npc_manager: NPCAgentManager,
    batch_dialogue_generator: BatchDialogueGenerator,
    background_cache: BackgroundDialogueCache,
    state_manager: StateManager,
    force_refresh: bool = False,
) -> BatchBackgroundDialogueResult | None:
    """读取或生成背景对话，并同步NPC运行状态。"""

    # 读取当前尚未过期的背景对话缓存。
    cached_record = background_cache.load_valid()

    # 没有要求强制刷新且存在有效缓存时，
    # 直接返回缓存，不调用DeepSeek。
    if not force_refresh and cached_record is not None:
        # 计算缓存剩余时间。
        remaining_seconds = (
            background_cache.get_remaining_seconds(
                cache_record=cached_record,
            )
        )

        print(
            f"\n[已读取背景对话缓存，"
            f"剩余{remaining_seconds}秒]"
        )

        # 将缓存背景状态同步到StateManager。
        state_manager.update_background_states(
            background_result=cached_record.result,
        )

        return cached_record.result

    # 区分强制刷新和缓存自动过期。
    if force_refresh:
        print(
            "\n正在强制刷新所有NPC背景状态……"
        )
    else:
        print(
            "\n背景对话缓存不存在或已过期。"
        )
        print(
            "正在批量生成所有NPC的背景状态……"
        )

    # 根据电脑当前时间生成赛博小镇场景。
    scene_context = build_scene_context(
        weather="天气晴朗，微风轻柔",
        special_event=None,
    )

    try:
        # 获取全部NPC对象。
        npcs = npc_manager.get_all_npcs()

        # 一次API调用生成全部NPC背景状态。
        background_result = (
            batch_dialogue_generator.generate(
                npcs=npcs,
                scene_context=scene_context,
            )
        )

        # 使用新结果覆盖背景缓存。
        background_cache.save(
            scene_context=scene_context,
            result=background_result,
        )

        # 将新生成的背景状态同步到StateManager。
        state_manager.update_background_states(
            background_result=background_result,
        )        


        print("NPC背景状态批量生成成功。")
        print(
            f"[场景："
            f"{background_result.scene_summary}]"
        )

        return background_result

    except Exception as error:
        # 背景生成失败不影响玩家正常聊天。
        print(
            f"[NPC背景状态生成失败：{error}]"
        )

        # 强制刷新失败时继续使用旧缓存。
        if cached_record is not None:
            print(
                "[继续使用刷新前的背景对话缓存]"
            )
            # 恢复旧缓存对应的NPC状态。
            state_manager.update_background_states(
                background_result=cached_record.result,
            )
            return cached_record.result

        return None


def show_npc_menu(
    npc_manager: NPCAgentManager,
    background_result: (
        BatchBackgroundDialogueResult | None
    ),
    relationship_manager: RelationshipManager,
    player_id: str = DEFAULT_PLAYER_ID,
) -> list[NPC]:
    """显示全部NPC、背景状态和当前好感度。"""

    # 获取全部NPC对象。
    npcs = npc_manager.get_all_npcs()

    # 建立npc_id到背景状态的映射。
    background_map = {}

    if background_result is not None:
        background_map = {
            dialogue.npc_id: dialogue
            for dialogue in background_result.dialogues
        }

    print("\n========== 赛博小镇 ==========")

    # 显示当前场景概要。
    if background_result is not None:
        print(
            f"当前场景："
            f"{background_result.scene_summary}"
        )

    print("\n请选择要交谈的NPC：")

    # 显示NPC身份、好感度和背景状态。
    for index, npc in enumerate(
        npcs,
        start=1,
    ):
        # 读取玩家与当前NPC之间的好感度。
        relationship = (
            relationship_manager.get_relationship(
                npc_id=npc.npc_id,
                player_id=player_id,
            )
        )

        # 显示NPC身份。
        print(
            f"\n{index}. "
            f"{npc.name}——{npc.role}"
        )

        # 显示好感度等级和分数。
        print(
            f"   关系：{relationship.level}"
            f"（{relationship.score}/100）"
        )

        # 显示累计互动次数。
        print(
            f"   互动："
            f"{relationship.interaction_count}次"
        )

        # 查找当前NPC的背景状态。
        background_dialogue = background_map.get(
            npc.npc_id
        )

        if background_dialogue is not None:
            # 显示NPC当前动作。
            print(
                f"   动作："
                f"{background_dialogue.action}"
            )

            # 显示NPC当前情绪。
            print(
                f"   情绪："
                f"{background_dialogue.emotion}"
            )

            # 显示NPC当前背景台词。
            print(
                f"   台词："
                f"“{background_dialogue.speech}”"
            )

        else:
            # 没有背景状态时显示默认内容。
            print(
                "   状态：正在进行日常活动"
            )

    # 显示菜单控制选项。
    print("\nr. 刷新所有NPC背景状态")
    print("0. 退出程序")
    print("==============================")

    return npcs


def run_town(
    npc_manager: NPCAgentManager,
    embedding_model: SentenceTransformer,
    memory_extractor: MemoryExtractor,
    memory_query_planner: MemoryQueryPlanner,
    relationship_manager: RelationshipManager,
    batch_dialogue_generator: BatchDialogueGenerator,
    background_cache: BackgroundDialogueCache,
    state_manager: StateManager,
) -> None:
    """运行赛博小镇NPC选择菜单。"""

    # 只在进入run_town()时初始化一次。
    #
    # 不能放进while循环，
    # 否则输入r后会立即恢复为False。
    force_refresh = False

    while True:
        # 根据force_refresh决定读取缓存或重新生成。
        background_result = (
            get_or_generate_background_dialogues(
                npc_manager=npc_manager,
                batch_dialogue_generator=(
                    batch_dialogue_generator
                ),
                background_cache=background_cache,
                state_manager=state_manager,
                force_refresh=force_refresh,
            )
        )

        # 本轮刷新请求已经处理完成。
        force_refresh = False

        # 显示NPC、背景状态和好感度。
        npcs = show_npc_menu(
            npc_manager=npc_manager,
            background_result=background_result,
            relationship_manager=relationship_manager,
            player_id=DEFAULT_PLAYER_ID,
        )

        # 读取玩家菜单选择。
        choice = input(
            "\n请输入NPC编号："
        ).strip()

        # 玩家输入r或“刷新”时强制重新生成。
        if (
            choice.lower() == "r"
            or choice == "刷新"
        ):
            force_refresh = True
            continue

        # 玩家输入退出命令时结束程序。
        if choice in {
            "0",
            "退出",
            "exit",
            "quit",
        }:
            print("你离开了赛博小镇。")
            return

        # NPC编号必须是数字。
        if not choice.isdigit():
            print("请输入正确的NPC编号。")
            continue

        # 将菜单编号转换成列表索引。
        npc_index = int(choice) - 1

        # 检查NPC编号是否存在。
        if (
            npc_index < 0
            or npc_index >= len(npcs)
        ):
            print("没有这个NPC，请重新选择。")
            continue

        # 获取玩家选中的NPC。
        selected_npc = npcs[npc_index]

        print(
            f"\n你来到了"
            f"{selected_npc.name}面前。"
        )

        print(
            f"{selected_npc.name}的身份："
            f"{selected_npc.role}"
        )

        # 尝试占用当前NPC。
        #
        # 检查状态和设置忙碌会在同一次加锁操作中完成。
        interaction_started = (
            state_manager.try_begin_interaction(
                npc_id=selected_npc.npc_id,
                player_id=DEFAULT_PLAYER_ID,
            )
        )

        # NPC已经被其他玩家占用时拒绝进入。
        if not interaction_started:
            print(
                f"{selected_npc.name}当前正在与其他玩家交谈，"
                "请稍后再试。"
            )
            continue

        try:
            # NPC已进入talking状态，开始实时对话。
            run_chat(
                npc=selected_npc,
                embedding_model=embedding_model,
                memory_extractor=memory_extractor,
                memory_query_planner=memory_query_planner,
                relationship_manager=relationship_manager,
                player_id=DEFAULT_PLAYER_ID,
            )

        finally:
            # 无论正常返回、主动退出还是发生异常，
            # 都必须释放NPC，避免NPC永久处于忙碌状态。
            state_manager.end_interaction(
                npc_id=selected_npc.npc_id,
                player_id=DEFAULT_PLAYER_ID,
            )


def main() -> None:
    """程序主函数。"""

    # 读取.env中的DeepSeek配置。
    api_key, base_url, model = load_config()

    print("配置读取成功")
    print(f"API地址：{base_url}")
    print(f"模型名称：{model}")
    print("API密钥：已读取，不显示具体内容")

    # 创建DeepSeek客户端。
    client = create_llm_client(
        api_key=api_key,
        base_url=base_url,
    )

    print("LLM客户端创建成功")

    # 加载中文Embedding模型。
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

    print("长期记忆提取器创建成功")

    # 创建长期记忆查询规划器。
    memory_query_planner = MemoryQueryPlanner(
        client=client,
        model=model,
    )

    print("长期记忆查询规划器创建成功")

    # 创建玩家态度分析器。
    affinity_analyzer = AffinityAnalyzer(
        client=client,
        model=model,
    )

    print("玩家态度分析器创建成功")

    # 创建好感度管理器。
    relationship_manager = RelationshipManager(
        analyzer=affinity_analyzer,
    )

    print("好感度管理器创建成功")

    # 创建NPC管理器。
    npc_manager = NPCAgentManager(
        client=client,
        model=model,
    )

    # 初始化全部NPC。
    npc_manager.initialize_npcs()

    # 创建NPC运行状态管理器。
    state_manager = StateManager()

    # 使用NPC管理器中的全部NPC初始化状态。
    state_manager.initialize_npcs(
        npcs=npc_manager.get_all_npcs(),
    )

    print(
        f"NPC状态管理器初始化成功，"
        f"当前共有{state_manager.get_npc_count()}个状态。"
    )
    

    print(
        f"NPC管理器初始化成功，"
        f"当前共有"
        f"{npc_manager.get_npc_count()}个NPC。"
    )

    # 创建NPC批量背景对话生成器。
    batch_dialogue_generator = (
        BatchDialogueGenerator(
            client=client,
            model=model,
        )
    )

    print("批量背景对话生成器创建成功")

    # 创建背景对话缓存管理器。
    #
    # 300秒等于5分钟。
    background_cache = BackgroundDialogueCache(
        ttl_seconds=300,
    )

    print("背景对话缓存管理器创建成功")

    # 正式进入赛博小镇。
    run_town(
        npc_manager=npc_manager,
        embedding_model=embedding_model,
        memory_extractor=memory_extractor,
        memory_query_planner=memory_query_planner,
        relationship_manager=relationship_manager,
        batch_dialogue_generator=(
            batch_dialogue_generator
        ),
        background_cache=background_cache,
        state_manager=state_manager,
    )


# 只有直接运行main.py时才启动程序。
if __name__ == "__main__":
    main()