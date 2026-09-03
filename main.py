"""
玩家输入
→ 读取conversation_history
→ 组合系统提示词、历史记录和当前消息
→ 调用DeepSeek
→ 获得NPC回复
→ 保存user消息
→ 保存assistant回复
→ 超过5轮时删除最早记录
"""

import os
import re
from dotenv import load_dotenv
from openai import OpenAI
from sentence_transformers import SentenceTransformer
import json
from pathlib import Path
import numpy as np

NPC_PROFILE = {
    "name": "林舟",
    "role": "赛博小镇物资管理员",
    "personality": "沉稳、友善、说话简洁，对小镇的物资和居民比较了解",
}
NPC_PROFILE["name"]          # NPC姓名
NPC_PROFILE["role"]          # NPC职业
NPC_PROFILE["personality"]   # NPC性格

# 短期记忆最多保存5轮，一轮包含一条玩家消息和一条NPC回复
MAX_HISTORY_ROUNDS = 5

PROJECT_ROOT = Path(__file__).resolve().parent
MEMORY_FILE = PROJECT_ROOT / "data" / "lin_zhou_memory.json"
VECTOR_MEMORY_FILE = PROJECT_ROOT / "data" / "lin_zhou_vector_memory.json"

EMBEDDING_MODEL_NAME = "BAAI/bge-small-zh-v1.5"



# 相似度低于该值的记忆不返回
MIN_SIMILARITY = 0.55

def load_config():
    """读取并检查LLM配置。"""

    # 将.env中的变量加载到当前程序环境
    load_dotenv()

    api_key = os.getenv("LLM_API_KEY")
    base_url = os.getenv("LLM_BASE_URL")
    model = os.getenv("LLM_MODEL")

    # 找出没有填写的配置项
    config = {
        "LLM_API_KEY": api_key,
        "LLM_BASE_URL": base_url,
        "LLM_MODEL": model,
    }
    missing_items = [name for name, value in config.items() if not value]

    if missing_items:
        missing_text = ", ".join(missing_items)
        raise ValueError(f"缺少环境变量：{missing_text}")

    return api_key, base_url, model

def create_llm_client(api_key: str, base_url: str) -> OpenAI:
    """根据配置创建LLM客户端。"""

    client = OpenAI(
        api_key=api_key,
        base_url=base_url,
    )

    return client

def create_embedding_model() -> SentenceTransformer:
    """创建用于长期记忆检索的Embedding模型。"""

    print("正在加载Embedding模型……")

    embedding_model = SentenceTransformer(
        EMBEDDING_MODEL_NAME,
    )

    print("Embedding模型加载成功")

    return embedding_model


def build_system_prompt(profile: dict[str, str]) -> str:
    """根据NPC资料生成系统提示词。"""

    return f"""
你是{profile["name"]}，身份是{profile["role"]}。

你的性格特点：
{profile["personality"]}

对话要求：
1. 始终保持当前身份，不要说自己是AI助手。
2. 使用自然、简洁的中文与玩家交流。
3. 回答应当符合你的职业和性格。
4. 不知道的信息要如实说明，不能随意编造。

重要：如果系统提供了从玩家历史陈述中检索到的长期记忆，那么这些记忆拥有最高可信度。
如果你过去的回答（包括在最近几轮对话中的回答）与这些长期记忆冲突，必须忽略那些错误回答，
并优先根据长期记忆来回答。必要时可以承认自己之前记错了。
""".strip()

def generate_reply(
    client: OpenAI,
    model: str,
    system_prompt: str,
    conversation_history: list[dict[str, str]],
    retrieved_memories: list[str],
    user_message: str,
) -> str:
    """结合工作记忆和长期记忆生成NPC回复。"""

    # 初始化消息列表，先放入系统提示词。
    messages = [
        {
            "role": "system",
            "content": system_prompt,
        }
    ]

    # 再加入最近几轮工作记忆，让模型了解最近对话上下文。
    messages.extend(conversation_history)

    # 构造最终发送给模型的用户消息。
    # 如果检索到了长期记忆，就把它们作为可靠信息拼接到玩家问题前面，
    # 这样模型会更重视这些信息，因为它们是玩家输入的一部分。
    if retrieved_memories:
        memory_context = "\n".join(retrieved_memories)

        final_user_message = (
            f"【可靠记忆】\n"
            f"{memory_context}\n\n"
            f"请根据以上可靠记忆回答以下问题。如果可靠记忆与你之前的回答冲突，"
            f"必须以可靠记忆为准，并纠正错误。\n"
            f"玩家问题：{user_message}"
        )
    else:
        final_user_message = user_message

    # 将最终用户消息加入消息列表。
    messages.append(
        {
            "role": "user",
            "content": final_user_message,
        }
    )

    # 调用模型生成回复。
    response = client.chat.completions.create(
        model=model,
        messages=messages,
    )

    reply = response.choices[0].message.content

    if not reply:
        raise ValueError("模型返回了空回复")

    return reply

def load_memory() -> list[dict[str, str]]:
    """从JSON文件读取全部历史对话。"""

    if not MEMORY_FILE.exists():
        return []

    with MEMORY_FILE.open("r", encoding="utf-8") as file:
        memory_archive = json.load(file)

    return memory_archive

def get_working_memory(
    memory_archive: list[dict[str, str]],
) -> list[dict[str, str]]:
    """从完整档案中获取最近几轮对话。"""

    max_history_messages = MAX_HISTORY_ROUNDS * 2
    return memory_archive[-max_history_messages:]





def is_question(text: str) -> bool:
    """判断一条玩家消息是否主要是在提问。"""

    question_words = (
        "什么",
        "多少",
        "是谁",
        "哪",
        "怎么",
        "为什么",
        "是否",
        "吗",
    )

    return (
        "？" in text
        or "?" in text
        or any(word in text for word in question_words)
    )

def retrieve_relevant_memories(
    vector_memories: list[dict],
    query: str,
    embedding_model: SentenceTransformer,
    top_k: int = 3,
    min_similarity: float = MIN_SIMILARITY,
) -> list[str]:
    """从持久化向量记忆中检索相关事实。"""

    if not vector_memories:
        return []

    query_embedding = embedding_model.encode(
        query,
        normalize_embeddings=True,
    )

    memory_embeddings = np.asarray(
        [
            memory["embedding"]
            for memory in vector_memories
        ],
        dtype=np.float32,
    )

    similarities = memory_embeddings @ query_embedding

    scored_memories = [
        (
            float(similarity),
            vector_memories[index]["content"],
        )
        for index, similarity in enumerate(similarities)
        if float(similarity) >= min_similarity
    ]

    scored_memories.sort(
        key=lambda item: item[0],
        reverse=True,
    )

    return [
        (
            f"玩家以前主动提供的信息：{content}"
            f"（语义相似度：{score:.4f}）"
        )
        for score, content in scored_memories[:top_k]
    ]


def save_memory(conversation_history: list[dict[str, str]]) -> None:
    """将NPC记忆保存到JSON文件。"""

    # data目录不存在时自动创建
    MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)

    with MEMORY_FILE.open("w", encoding="utf-8") as file:
        json.dump(
            conversation_history,
            file,
            ensure_ascii=False,
            indent=2,
        )

def load_vector_memory() -> list[dict]:
    """读取已经生成Embedding的长期记忆。"""

    if not VECTOR_MEMORY_FILE.exists():
        return []

    with VECTOR_MEMORY_FILE.open("r", encoding="utf-8") as file:
        return json.load(file)


def save_vector_memory(vector_memories: list[dict]) -> None:
    """保存长期记忆向量文本及其Embedding向量。"""

    #.mkdir(...)：创建这个文件夹，如果父文件夹不存在也一并创建，exist_ok=True表示如果文件夹已经存在就不报错。
    VECTOR_MEMORY_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with VECTOR_MEMORY_FILE.open("w", encoding="utf-8") as file:
        json.dump(
            vector_memories,
            file,
            ensure_ascii=False,
            indent=2,
        )

def run_chat(
    client: OpenAI,
    model: str,
    system_prompt: str,
    embedding_model: SentenceTransformer,
) -> None:
    """持续对话，并管理工作记忆、完整档案和向量记忆。"""

    # 读取原始JSON中的全部历史对话
    memory_archive = load_memory()

    # 从完整历史中选择最近5轮作为工作记忆
    conversation_history = get_working_memory(
        memory_archive
    )

    # 读取已经生成Embedding的长期向量记忆
    vector_memories = load_vector_memory()

    # 如果向量记忆为空，就把旧对话迁移进去
    if not vector_memories:
        for message in memory_archive:
            # 只迁移玩家说过的话
            if message.get("role") != "user":
                continue

            # 获取玩家消息
            content = message.get("content", "").strip()

            # 跳过空消息和问题
            if not content or is_question(content):
                continue

            # 生成向量并保存
            add_vector_memory(
                vector_memories=vector_memories,
                user_message=content,
                embedding_model=embedding_model,
            )

        # 显示迁移结果
        print(f"旧记忆迁移完成，共{len(vector_memories)}条。")

    # 显示当前各种记忆的数量
    print(
        f"\n已保存{len(memory_archive) // 2}轮历史，"
        f"本次加载最近{len(conversation_history) // 2}轮。"
    )

    # 显示向量记忆数量
    print(
        f"已加载{len(vector_memories)}条长期向量记忆。"
    )

    # 提示玩家如何退出
    print("对话已经开始，输入“退出”可以结束程序。")

    # 持续接收玩家输入
    while True:
        # 获取并清理玩家输入
        user_message = input("\n你：").strip()

        # 玩家输入退出指令时结束程序
        if user_message in {"退出", "exit", "quit"}:
            print("对话结束。")
            break

        # 阻止发送空消息
        if not user_message:
            print("输入不能为空，请重新输入。")
            continue

        # 显示NPC思考提示
        print(f"{NPC_PROFILE['name']}正在思考……")

        try:
            # 从持久化向量记忆中检索相关内容
            retrieved_memories = retrieve_relevant_memories(
                vector_memories=vector_memories,
                query=user_message,
                embedding_model=embedding_model,
            )

            # 显示检索到的长期记忆数量
            print(
                f"[检索到{len(retrieved_memories)}"
                f"条相关长期记忆]"
            )

            # 显示每条长期记忆，方便检查检索效果
            for index, memory in enumerate(
                retrieved_memories,
                start=1,
            ):
                print(f"[长期记忆{index}] {memory}")

            # 将系统提示词、工作记忆、长期记忆和当前问题交给LLM
            reply = generate_reply(
                client=client,
                model=model,
                system_prompt=system_prompt,
                conversation_history=conversation_history,
                retrieved_memories=retrieved_memories,
                user_message=user_message,
            )

        # 捕获检索或模型调用中的错误
        except Exception as error:
            print(f"调用模型失败：{error}")
            continue

        # 输出NPC回复
        print(f"\n{NPC_PROFILE['name']}：{reply}")

        # 把本轮玩家消息加入完整对话档案
        memory_archive.append(
            {
                "role": "user",
                "content": user_message,
            }
        )

        # 把本轮NPC回复加入完整对话档案
        memory_archive.append(
            {
                "role": "assistant",
                "content": reply,
            }
        )

        # 将更新后的完整对话保存到原始JSON文件
        save_memory(memory_archive)

        # 尝试把玩家本轮提供的事实写入向量记忆
        # 如果本轮是问题，add_vector_memory()会自动跳过
        add_vector_memory(
            vector_memories=vector_memories,
            user_message=user_message,
            embedding_model=embedding_model,
        )

        # 重新获取最近5轮，供下一轮对话使用
        conversation_history = get_working_memory(
            memory_archive
        )

        # 显示三种记忆的当前数量
        print(
            f"[完整档案：{len(memory_archive) // 2}轮；"
            f"工作记忆：{len(conversation_history) // 2}轮；"
            f"向量记忆：{len(vector_memories)}条]"
        )

def add_vector_memory(
    vector_memories: list[dict],
    user_message: str,
    embedding_model: SentenceTransformer,
) -> None:
    """将玩家主动提供的信息写入向量记忆。"""

    content = user_message.strip()

    if not content:
        return

    # 问题不属于玩家主动提供的事实
    if is_question(content):
        return

    # 避免完全相同的记忆重复保存
    existing_contents = {
        memory["content"]
        for memory in vector_memories
    }

    if content in existing_contents:
        return

    embedding = embedding_model.encode(
        content,
        normalize_embeddings=True,
    )

    vector_memories.append(
        {
            "content": content,
            "embedding": embedding.tolist(),
        }
    )

    save_vector_memory(vector_memories)

    print(f"[新增长期向量记忆] {content}")

def main():
    """创建所有组件并启动NPC对话。"""

    # 读取环境变量中的LLM配置
    api_key, base_url, model = load_config()

    # 显示配置读取结果
    print("配置读取成功")
    print(f"API地址：{base_url}")
    print(f"模型名称：{model}")
    print("API密钥：已读取，不显示具体内容")

    # 创建DeepSeek客户端
    client = create_llm_client(
        api_key,
        base_url,
    )
    print("LLM客户端创建成功")

    # 加载本地Embedding模型
    embedding_model = create_embedding_model()

    # 根据NPC资料构建系统提示词
    system_prompt = build_system_prompt(
        NPC_PROFILE
    )

    # 显示NPC信息
    print("NPC角色创建成功")
    print(f"当前NPC：{NPC_PROFILE['name']}")
    print(f"NPC身份：{NPC_PROFILE['role']}")

    # 启动对话，并传入Embedding模型
    run_chat(
        client=client,
        model=model,
        system_prompt=system_prompt,
        embedding_model=embedding_model,
    )

    

if __name__ == "__main__":
    main()