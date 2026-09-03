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

EMBEDDING_MODEL_NAME = "BAAI/bge-small-zh-v1.5"

# 查询指令只添加到问题，不添加到历史记忆
QUERY_INSTRUCTION = "为这个句子生成表示以用于检索相关文章："

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
    memory_archive: list[dict[str, str]],
    query: str,
    embedding_model: SentenceTransformer,
    top_k: int = 3,
    min_similarity: float = MIN_SIMILARITY,
) -> list[str]:
    """使用Embedding检索玩家过去主动陈述的相关事实。"""

    max_working_messages = MAX_HISTORY_ROUNDS * 2

    # 最近5轮已经在工作记忆中，不再重复检索
    long_term_messages = memory_archive[:-max_working_messages]

    if not long_term_messages:
        return []

    candidate_memories: list[str] = []

    for message in long_term_messages:
        # 只把玩家主动提供的内容作为事实候选
        if message.get("role") != "user":
            continue

        content = message.get("content", "").strip()

        if not content:
            continue

        # 玩家过去提出的问题不作为事实
        if is_question(content):
            continue

        candidate_memories.append(content)

    if not candidate_memories:
        return []

    # 查询添加检索指令
    query_text = QUERY_INSTRUCTION + query

    # 将当前问题转换成一个向量
    query_embedding = embedding_model.encode(
        query_text,
        normalize_embeddings=True,
    )

    # 一次性将全部候选记忆转换成向量
    memory_embeddings = embedding_model.encode(
        candidate_memories,
        normalize_embeddings=True,
    )

    # 向量已经归一化，点积结果就是余弦相似度
    similarities = memory_embeddings @ query_embedding

    scored_memories: list[tuple[float, str]] = []

    for content, similarity in zip(
        candidate_memories,
        similarities,
    ):
        similarity_score = float(similarity)

        if similarity_score >= min_similarity:
            scored_memories.append(
                (
                    similarity_score,
                    content,
                )
            )

    # 按语义相似度从高到低排序
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

def run_chat(
    client: OpenAI,
    model: str,
    system_prompt: str,
    embedding_model: SentenceTransformer,
) -> None:
    """持续对话，并管理完整档案和工作记忆。"""

    # 读取磁盘中的全部历史
    memory_archive = load_memory()

    # 从全部历史中选择最近5轮
    conversation_history = get_working_memory(memory_archive)

    print(
        f"\n已保存{len(memory_archive) // 2}轮历史，"
        f"本次加载最近{len(conversation_history) // 2}轮。"
    )
    print("对话已经开始，输入“退出”可以结束程序。")

    while True:
        user_message = input("\n你：").strip()

        if user_message in {"退出", "exit", "quit"}:
            print("对话结束。")
            break

        if not user_message:
            print("输入不能为空，请重新输入。")
            continue

        print(f"{NPC_PROFILE['name']}正在思考……")

        try:

            retrieved_memories = retrieve_relevant_memories(
                memory_archive=memory_archive,
                query=user_message,
                embedding_model=embedding_model,
            )

            print(f"[检索到{len(retrieved_memories)}条相关长期记忆]")

            for index, memory in enumerate(retrieved_memories, start=1):
                print(f"[长期记忆{index}] {memory}")
            
            reply = generate_reply(
                client=client,
                model=model,
                system_prompt=system_prompt,
                conversation_history=conversation_history,
                retrieved_memories=retrieved_memories,
                user_message=user_message,
            )
        except Exception as error:
            print(f"调用模型失败：{error}")
            continue

        print(f"\n{NPC_PROFILE['name']}：{reply}")

        # 将本轮对话加入完整档案
        memory_archive.append(
            {
                "role": "user",
                "content": user_message,
            }
        )
        memory_archive.append(
            {
                "role": "assistant",
                "content": reply,
            }
        )

        # 永久保存完整档案
        save_memory(memory_archive)

        # 重新提取最近5轮，作为下一次请求的工作记忆
        conversation_history = get_working_memory(memory_archive)

        print(
            f"[完整档案：{len(memory_archive) // 2}轮；"
            f"工作记忆：{len(conversation_history) // 2}轮]"
        )


def main():
    api_key, base_url, model = load_config()

    print("配置读取成功")
    print(f"API地址：{base_url}")
    print(f"模型名称：{model}")
    print("API密钥：已读取，不显示具体内容")

    client = create_llm_client(api_key, base_url)
    
    print("LLM客户端创建成功")
    embedding_model = create_embedding_model()

    system_prompt = build_system_prompt(NPC_PROFILE)

    print("NPC角色创建成功")
    print(f"当前NPC：{NPC_PROFILE['name']}")
    print(f"NPC身份：{NPC_PROFILE['role']}")

    run_chat(
        client=client,
        model=model,
        system_prompt=system_prompt,
        embedding_model=embedding_model,
    )

    

if __name__ == "__main__":
    main()