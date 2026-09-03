"""
main.py

程序主入口，负责：

1. 读取LLM配置；
2. 创建DeepSeek客户端；
3. 加载Embedding模型；
4. 创建长期记忆提取器；
5. 初始化全部NPC；
6. 显示NPC选择菜单；
7. 管理玩家与NPC之间的对话；
8. 调用长期记忆检索和结构化记忆提取。
"""

from openai import OpenAI
from sentence_transformers import SentenceTransformer

from agents import NPCAgentManager
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
from npc import NPC

# MemoryQueryPlanner负责分析玩家正在查询哪类长期记忆。
from memory_query_planner import MemoryQueryPlanner

# Embedding模型名称：
# 用于把玩家问题和长期记忆转换成向量。
EMBEDDING_MODEL_NAME = "BAAI/bge-small-zh-v1.5"


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
) -> None:
    """运行玩家与指定NPC之间的持续对话。"""

    # npc_id用于区分不同NPC的独立记忆文件。
    npc_id = npc.npc_id

    # 加载当前NPC的全部原始对话档案。
    memory_archive = load_memory(npc_id=npc_id)

    # 从完整对话档案中提取最近几轮工作记忆。
    conversation_history = get_working_memory(
        memory_archive=memory_archive,
    )

    # 加载当前NPC的结构化长期向量记忆。
    vector_memories = load_vector_memory(
        npc_id=npc_id,
    )

    # 显示当前NPC的记忆状态。
    print(
        f"\n已保存{len(memory_archive) // 2}轮历史，"
        f"本次加载最近{len(conversation_history) // 2}轮，"
        f"长期向量记忆{len(vector_memories)}条。"
    )

    print("输入“返回”可以选择其他NPC。")
    print("输入“退出”可以结束程序。")

    while True:
        # 读取并清理玩家输入。
        user_message = input("\n你：").strip()

        # “退出”用于结束整个程序。
        if user_message in {"退出", "exit", "quit"}:
            print("对话结束。")
            raise SystemExit

        # “返回”只结束当前NPC的对话。
        if user_message in {"返回", "back"}:
            print(f"你结束了与{npc.name}的对话。")
            return

        # 不向模型发送空消息。
        if not user_message:
            print("输入不能为空，请重新输入。")
            continue

        print(f"{npc.name}正在思考……")

        # 第一步：让DeepSeek分析当前问题是否需要长期记忆，
        # 并推断可能对应的memory_key。
        try:
            query_plan = memory_query_planner.plan(
                user_message=user_message,
            )

            # 显示查询规划结果，方便观察系统行为。
            print(
                "[记忆查询计划："
                f"需要记忆={query_plan.needs_memory}；"
                f"记忆键={query_plan.memory_keys}；"
                f"语义查询={query_plan.semantic_query or '无'}；"
                f"置信度={query_plan.confidence:.2f}]"
            )

            # 显示规划原因，方便调试错误查询。
            if query_plan.reason:
                print(
                    f"[查询规划原因：{query_plan.reason}]"
                )

        except Exception as error:
            # 查询规划失败时设置为None。
            #
            # retrieve_relevant_memories()收到None后，
            # 会退回到旧版纯Embedding检索，
            # 不会影响玩家正常对话。
            print(f"[记忆查询规划失败：{error}]")
            query_plan = None

        # 第二步：执行memory_key精确匹配和Embedding语义检索。
        try:
            retrieved_memories = retrieve_relevant_memories(
                vector_memories=vector_memories,
                query=user_message,
                embedding_model=embedding_model,
                query_plan=query_plan,
            )

        except Exception as error:
            # 长期记忆检索失败时，
            # NPC仍然可以使用工作记忆正常回复。
            print(f"[长期记忆检索失败：{error}]")
            retrieved_memories = []
                # 显示检索结果，方便学习和调试。


        print(f"[检索到{len(retrieved_memories)}条相关长期记忆]")

        for index, memory in enumerate(
            retrieved_memories,
            start=1,
        ):
            print(f"[长期记忆{index}] {memory}")

        # 结合角色设定、工作记忆和长期记忆生成回复。
        try:
            reply = npc.generate_reply(
                conversation_history=conversation_history,
                retrieved_memories=retrieved_memories,
                user_message=user_message,
            )
        except Exception as error:
            print(f"调用模型失败：{error}")
            continue

        # 输出NPC回复。
        print(f"\n{npc.name}：{reply}")

        # 将玩家消息加入完整原始对话档案。
        memory_archive.append(
            {
                "role": "user",
                "content": user_message,
            }
        )

        # 将NPC回复加入完整原始对话档案。
        memory_archive.append(
            {
                "role": "assistant",
                "content": reply,
            }
        )

        # 每轮对话结束后立即保存原始档案，
        # 避免程序异常退出时丢失对话。
        try:
            save_memory(
                npc_id=npc_id,
                memory_archive=memory_archive,
            )
        except Exception as error:
            print(f"[原始对话档案保存失败：{error}]")

        # 重新截取最近几轮，作为下一轮工作记忆。
        conversation_history = get_working_memory(
            memory_archive=memory_archive,
        )

        # 只把本轮原始玩家消息交给记忆提取器。
        #
        # 不传入NPC回复，防止NPC编造的内容进入长期记忆；
        # 不传入历史记录，减少旧内容对本轮提取结果的干扰。
        try:
            extraction_result = memory_extractor.extract(
                user_message=user_message,
            )

            # 应用提取结果：
            # REMEMBER ->新增或更新记忆；
            # FORGET   ->删除对应记忆；
            # NONE     ->不做任何处理。
            # 应用长期记忆提取结果。

            # vector_memories是当前NPC已经加载的结构化长期记忆，
            # 函数会根据memory_key判断新增、更新或删除。
            memory_statistics = apply_memory_extraction(
                npc_id=npc_id,
                vector_memories=vector_memories,
                extraction_result=extraction_result,
                embedding_model=embedding_model,
            )

            # 显示本轮结构化记忆处理结果。
            print(
                "[长期记忆处理："
                f"新增{memory_statistics['added']}条，"
                f"更新{memory_statistics['updated']}条，"
                f"删除{memory_statistics['deleted']}条，"
                f"跳过{memory_statistics['skipped']}条]"
            )

        except Exception as error:
            # 记忆提取失败不应该导致正常对话中断。
            print(f"[长期记忆提取失败：{error}]")

        # 重新读取向量记忆。
        #
        # 这样本轮新增、更新或删除的记忆，
        # 可以在下一轮对话中立即参与检索。
        try:
            vector_memories = load_vector_memory(
                npc_id=npc_id,
            )
        except Exception as error:
            print(f"[长期向量记忆加载失败：{error}]")
            vector_memories = []

        # 显示当前NPC三种记忆的数量。
        print(
            f"[完整档案：{len(memory_archive) // 2}轮；"
            f"工作记忆：{len(conversation_history) // 2}轮；"
            f"向量记忆：{len(vector_memories)}条]"
        )


def show_npc_menu(
    npc_manager: NPCAgentManager,
) -> list[NPC]:
    """显示全部NPC，并返回NPC列表。"""

    # 从NPC管理器中取得所有NPC对象。
    npcs = npc_manager.get_all_npcs()

    print("\n========== 赛博小镇 ==========")
    print("请选择要交谈的NPC：")

    # 根据NPC数量动态生成菜单。
    for index, npc in enumerate(npcs, start=1):
        print(f"{index}. {npc.name}——{npc.role}")

    print("0. 退出程序")
    print("==============================")

    return npcs


def run_town(
    npc_manager: NPCAgentManager,
    embedding_model: SentenceTransformer,
    memory_extractor: MemoryExtractor,
    memory_query_planner: MemoryQueryPlanner,
) -> None:
    """运行赛博小镇NPC选择菜单。"""

    while True:
        # 每次返回小镇时重新显示NPC列表。
        npcs = show_npc_menu(
            npc_manager=npc_manager,
        )

        # 读取玩家的NPC选择。
        choice = input("\n请输入NPC编号：").strip()

        # 输入0或退出命令时结束程序。
        if choice in {"0", "退出", "exit", "quit"}:
            print("你离开了赛博小镇。")
            return

        # 菜单编号必须是数字。
        if not choice.isdigit():
            print("请输入正确的NPC编号。")
            continue

        # 将字符串编号转换成列表索引。
        npc_index = int(choice) - 1

        # 检查编号是否超出NPC列表范围。
        if npc_index < 0 or npc_index >= len(npcs):
            print("没有这个NPC，请重新选择。")
            continue

        # 获取玩家选中的NPC。
        selected_npc = npcs[npc_index]

        print(
            f"\n你来到了{selected_npc.name}面前。"
        )
        print(
            f"{selected_npc.name}的身份："
            f"{selected_npc.role}"
        )

        # 开始与选中的NPC对话。
        run_chat(
            npc=selected_npc,
            embedding_model=embedding_model,
            memory_extractor=memory_extractor,
            memory_query_planner=memory_query_planner,
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
    #
    # 第一次运行可能需要从本地缓存加载较长时间，
    # 后续运行通常会更快。
    print(f"正在加载Embedding模型：{EMBEDDING_MODEL_NAME}")

    embedding_model = SentenceTransformer(
        EMBEDDING_MODEL_NAME,
    )

    print("Embedding模型加载成功")

    # 创建长期记忆提取器。
    #
    # 它与NPC对话使用同一个DeepSeek客户端，
    # 但每次API请求彼此独立，不共享messages。
    memory_extractor = MemoryExtractor(
        client=client,
        model=model,
    )

    print("长期记忆提取器创建成功")

    # 创建长期记忆查询规划器。
    # 它负责在NPC回复之前判断：
    # 是否需要长期记忆、需要哪个memory_key、
    # 以及应该使用什么文本进行语义检索。
    memory_query_planner = MemoryQueryPlanner(
        client=client,
        model=model,
    )

    print("长期记忆查询规划器创建成功")

    # 创建NPC管理器并初始化全部NPC。
    npc_manager = NPCAgentManager(
        client=client,
        model=model,
    )

    npc_manager.initialize_npcs()

    print(
        f"NPC管理器初始化成功，"
        f"当前共有{npc_manager.get_npc_count()}个NPC。"
    )

    # 正式进入赛博小镇。
    run_town(
        npc_manager=npc_manager,
        embedding_model=embedding_model,
        memory_extractor=memory_extractor,
        memory_query_planner=memory_query_planner,
    )


# 只有直接运行main.py时才启动程序。
if __name__ == "__main__":
    main()