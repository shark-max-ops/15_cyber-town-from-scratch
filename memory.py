"""
NPC结构化记忆管理模块。

MemoryQueryPlan
├── memory_key精确匹配：最高优先级
└── Embedding语义匹配：补充召回
          ↓
结合重要性、可信度和时间计算综合分数


主要常量含义：
- MAX_HISTORY_ROUNDS：发送给NPC的最近对话轮数。
- MIN_SIMILARITY：长期记忆检索的最低语义相似度。
- MIN_CONFIDENCE：候选记忆允许保存的最低置信度。
- MIN_IMPORTANCE：候选记忆允许保存的最低重要度。
- DUPLICATE_SIMILARITY：判断语义重复的相似度标准。
- PROJECT_ROOT：项目根目录。
- DATA_DIR：全部NPC记忆文件所在目录。

主要变量含义：
- npc_id：NPC唯一标识。
- memory_archive：完整原始对话档案。
- conversation_history：最近几轮工作记忆。
- vector_memories：结构化长期向量记忆。
- extraction_result：DeepSeek返回的结构化记忆结果。
- candidate：一条候选记忆。
- query：玩家当前问题。
- embedding_model：本地Embedding模型。
- embedding：一条记忆对应的语义向量。
- similarities：查询与长期记忆的相似度。
- final_score：结合语义、重要度和时间得到的最终分数。
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import numpy as np
from pydantic import ValidationError
from sentence_transformers import SentenceTransformer

# 导入长期记忆相关的数据模型。
from memory_models import (
    MemoryExtractionResult,
    MemoryQueryPlan,
    StoredMemory,
)

# 最近5轮作为NPC工作记忆
MAX_HISTORY_ROUNDS = 5

# 长期记忆最低语义相似度
MIN_SIMILARITY = 0.50

# memory_key精确匹配的基础分数。
#
# 精确匹配意味着查询规划器和长期记忆使用了相同的结构化键，
# 因此优先级应该高于单纯的语义相似度。
EXACT_KEY_BASE_SCORE = 0.55

# 精确匹配后的语义相似度权重。
EXACT_SEMANTIC_WEIGHT = 0.20

# 非精确匹配时的语义相似度权重。
SEMANTIC_WEIGHT = 0.65

# 长期记忆重要性权重。
IMPORTANCE_WEIGHT = 0.15

# 长期记忆可信度权重。
CONFIDENCE_WEIGHT = 0.10

# 长期记忆时间新鲜度权重。
RECENCY_WEIGHT = 0.10

# 候选记忆最低置信度
MIN_CONFIDENCE = 0.70

# 候选记忆最低重要度
MIN_IMPORTANCE = 0.35

# 判断两条记忆语义重复的相似度
DUPLICATE_SIMILARITY = 0.97

# 当前项目根目录
PROJECT_ROOT = Path(__file__).resolve().parent

# 全部NPC记忆文件目录
DATA_DIR = PROJECT_ROOT / "data"


def get_memory_file(npc_id: str) -> Path:
    """获取指定NPC的完整对话文件。"""

    # 使用npc_id生成独立文件名
    return DATA_DIR / f"{npc_id}_memory.json"


def get_vector_memory_file(npc_id: str) -> Path:
    """获取指定NPC的结构化向量记忆文件。"""

    # 使用npc_id生成独立向量文件名
    return DATA_DIR / f"{npc_id}_vector_memory.json"


def load_memory(
    npc_id: str,
) -> list[dict[str, str]]:
    """读取指定NPC的全部原始对话。"""

    # 获取NPC对应的文件路径
    memory_file = get_memory_file(npc_id)

    # 文件不存在时返回空档案
    if not memory_file.exists():
        return []

    # 读取原始对话JSON
    with memory_file.open(
        "r",
        encoding="utf-8",
    ) as file:
        memory_archive = json.load(file)

    # 防止JSON最外层不是列表
    if not isinstance(memory_archive, list):
        raise ValueError("原始对话文件格式错误")

    # 返回完整对话
    return memory_archive


def save_memory(
    npc_id: str,
    memory_archive: list[dict[str, str]],
) -> None:
    """保存指定NPC的全部原始对话。"""

    # 获取NPC对应的文件路径
    memory_file = get_memory_file(npc_id)

    # 自动创建data目录
    memory_file.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    # 保存完整原始对话
    with memory_file.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            memory_archive,
            file,
            ensure_ascii=False,
            indent=2,
        )


def get_working_memory(
    memory_archive: list[dict[str, str]],
) -> list[dict[str, str]]:
    """从完整档案中获取最近几轮对话。"""

    # 一轮包含玩家消息和NPC回复两条消息
    max_history_messages = (
        MAX_HISTORY_ROUNDS * 2
    )

    # 返回最近几轮消息
    return memory_archive[-max_history_messages:]


def load_vector_memory(
    npc_id: str,
) -> list[dict]:
    """读取并校验指定NPC的结构化长期记忆。"""

    # 获取NPC对应的向量文件路径
    vector_file = get_vector_memory_file(npc_id)

    # 文件不存在时返回空列表
    if not vector_file.exists():
        return []

    # 读取向量记忆JSON
    with vector_file.open(
        "r",
        encoding="utf-8",
    ) as file:
        raw_memories = json.load(file)

    # 防止JSON最外层不是列表
    if not isinstance(raw_memories, list):
        raise ValueError("向量记忆文件格式错误")

    # 保存通过结构校验的记忆
    valid_memories: list[dict] = []

    # 记录旧版或损坏的记忆数量
    invalid_count = 0

    # 逐条验证记忆结构
    for raw_memory in raw_memories:
        try:
            # 使用Pydantic验证记忆字段
            stored_memory = StoredMemory.model_validate(
                raw_memory
            )

            # 转成可以写入JSON的字典
            valid_memories.append(
                stored_memory.model_dump(
                    mode="json"
                )
            )

        # 旧版记录缺少字段时跳过
        except ValidationError:
            invalid_count += 1

    # 显示被忽略的旧版记忆数量
    if invalid_count > 0:
        print(
            f"[记忆升级] 忽略{invalid_count}"
            f"条旧版向量记录"
        )

    # 返回有效结构化记忆
    return valid_memories


def save_vector_memory(
    npc_id: str,
    vector_memories: list[dict],
) -> None:
    """保存指定NPC的结构化向量记忆。"""

    # 获取NPC对应的向量文件路径
    vector_file = get_vector_memory_file(npc_id)

    # 自动创建data目录
    vector_file.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    # 保存结构化向量记忆
    with vector_file.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            vector_memories,
            file,
            ensure_ascii=False,
            indent=2,
        )


def _find_semantic_duplicate(
    vector_memories: list[dict],
    memory_type: str,
    embedding: np.ndarray,
) -> int | None:
    """查找语义几乎相同的已有记忆。"""

    # 遍历全部长期记忆
    for index, memory in enumerate(
        vector_memories
    ):
        # 不同类型的记忆不进行重复判断
        if memory.get("memory_type") != memory_type:
            continue

        # 读取已有记忆向量
        old_embedding = np.asarray(
            memory.get("embedding", []),
            dtype=np.float32,
        )

        # 缺少向量时无法比较
        if old_embedding.size == 0:
            continue

        # 向量维度不一致时跳过
        if old_embedding.shape != embedding.shape:
            continue

        # 计算两条记忆的语义相似度
        similarity = float(
            old_embedding @ embedding
        )

        # 相似度足够高时认为是同一事实
        if similarity >= DUPLICATE_SIMILARITY:
            return index

    # 没有找到重复记忆
    return None


def apply_memory_extraction(
    npc_id: str,
    vector_memories: list[dict],
    extraction_result: MemoryExtractionResult,
    embedding_model: SentenceTransformer,
) -> dict[str, int]:
    """执行DeepSeek提取出的长期记忆操作。"""

    # 统计本轮记忆操作结果
    statistics = {
        "added": 0,
        "updated": 0,
        "deleted": 0,
        "skipped": 0,
    }

    # 标记记忆文件是否发生变化
    memory_changed = False

    # 遍历本轮提取出的全部候选记忆
    for candidate in extraction_result.memories:
        # NONE不需要执行
        if candidate.action == "NONE":
            statistics["skipped"] += 1
            continue

        # 敏感信息禁止保存
        if candidate.sensitive:
            print(
                "[记忆安全] 检测到敏感信息，"
                "本条内容不会保存"
            )
            statistics["skipped"] += 1
            continue

        # 置信度过低时不保存
        if candidate.confidence < MIN_CONFIDENCE:
            statistics["skipped"] += 1
            continue

        # 重要度过低时不保存
        if candidate.importance < MIN_IMPORTANCE:
            statistics["skipped"] += 1
            continue

        # memory_key为空时无法更新和删除
        if not candidate.memory_key.strip():
            statistics["skipped"] += 1
            continue

        # 执行遗忘操作
        if candidate.action == "FORGET":
            # 记录删除前的数量
            original_count = len(vector_memories)

            # 删除具有相同memory_key的记忆
            vector_memories[:] = [
                memory
                for memory in vector_memories
                if memory.get("memory_key")
                != candidate.memory_key
            ]

            # 计算实际删除数量
            deleted_count = (
                original_count
                - len(vector_memories)
            )

            # 更新删除统计
            statistics["deleted"] += deleted_count

            # 实际删除后标记文件变化
            if deleted_count > 0:
                memory_changed = True

            continue

        # REMEMBER必须具有值和摘要
        if (
            not candidate.value.strip()
            or not candidate.summary.strip()
        ):
            statistics["skipped"] += 1
            continue

        # 为标准化摘要生成向量
        embedding = embedding_model.encode(
            candidate.summary,
            normalize_embeddings=True,
        )

        # 查找memory_key完全相同的记忆
        matching_indices = [
            index
            for index, memory
            in enumerate(vector_memories)
            if memory.get("memory_key")
            == candidate.memory_key
        ]

        # memory_key不同但语义高度相同时也视为重复
        if not matching_indices:
            duplicate_index = (
                _find_semantic_duplicate(
                    vector_memories=vector_memories,
                    memory_type=candidate.memory_type,
                    embedding=embedding,
                )
            )

            # 找到语义重复记忆时将其作为更新目标
            if duplicate_index is not None:
                matching_indices = [
                    duplicate_index
                ]

        # 获取当前UTC时间
        current_time = datetime.now(
            timezone.utc
        )

        # 已存在同类记忆时执行UPDATE
        if matching_indices:
            # 获取第一条旧记忆
            old_memory = vector_memories[
                matching_indices[0]
            ]

            # 内容没有变化时跳过重复保存
            if (
                old_memory.get("value")
                == candidate.value
                and old_memory.get("summary")
                == candidate.summary
            ):
                statistics["skipped"] += 1
                continue

            # 保留旧记忆ID和创建时间
            updated_memory = StoredMemory(
                memory_id=old_memory["memory_id"],
                memory_type=candidate.memory_type,
                memory_key=candidate.memory_key,
                value=candidate.value,
                summary=candidate.summary,
                importance=candidate.importance,
                confidence=candidate.confidence,
                source="player_statement",
                source_text=candidate.source_text,
                created_at=old_memory["created_at"],
                updated_at=current_time,
                embedding=embedding.tolist(),
            )

            # 删除所有相同key或重复记录
            indices_to_remove = set(
                matching_indices
            )

            vector_memories[:] = [
                memory
                for index, memory
                in enumerate(vector_memories)
                if index not in indices_to_remove
            ]

            # 加入更新后的记忆
            vector_memories.append(
                updated_memory.model_dump(
                    mode="json"
                )
            )

            # 更新统计数据
            statistics["updated"] += 1
            memory_changed = True

        # 不存在同类记忆时执行ADD
        else:
            # 创建全新的正式记忆
            new_memory = StoredMemory(
                memory_id=str(uuid4()),
                memory_type=candidate.memory_type,
                memory_key=candidate.memory_key,
                value=candidate.value,
                summary=candidate.summary,
                importance=candidate.importance,
                confidence=candidate.confidence,
                source="player_statement",
                source_text=candidate.source_text,
                created_at=current_time,
                updated_at=current_time,
                embedding=embedding.tolist(),
            )

            # 加入长期记忆列表
            vector_memories.append(
                new_memory.model_dump(
                    mode="json"
                )
            )

            # 更新统计数据
            statistics["added"] += 1
            memory_changed = True

    # 只有记忆发生变化时才写入文件
    if memory_changed:
        save_vector_memory(
            npc_id=npc_id,
            vector_memories=vector_memories,
        )

    # 返回本轮操作统计
    return statistics


def _calculate_cosine_similarity(
    first_embedding: list[float] | np.ndarray,
    second_embedding: list[float] | np.ndarray,
) -> float:
    """计算两个向量之间的余弦相似度。"""

    # 转换成NumPy数组，确保可以进行向量运算。
    first_vector = np.asarray(
        first_embedding,
        dtype=np.float32,
    )

    second_vector = np.asarray(
        second_embedding,
        dtype=np.float32,
    )

    # 计算两个向量的长度。
    first_norm = np.linalg.norm(first_vector)
    second_norm = np.linalg.norm(second_vector)

    # 防止空向量导致除零错误。
    if first_norm == 0 or second_norm == 0:
        return 0.0

    # 余弦相似度：
    # 点积 ÷ 两个向量长度的乘积。
    similarity = np.dot(
        first_vector,
        second_vector,
    ) / (
        first_norm * second_norm
    )

    return float(similarity)


def _calculate_recency_score(
    updated_at: str,
) -> float:
    """根据更新时间计算0到1之间的新近度。"""
    #输入：一个表示更新时间的 ISO 格式字符串（例如 "2026-09-01T12:34:56"）。
    #输出：一个 浮点数，范围在 (0, 1] 之间，越接近 1 表示越新。

    try:
        # 将ISO时间字符串转换为datetime
        memory_time = datetime.fromisoformat(
            updated_at
        )

        # 没有时区时默认使用UTC
        if memory_time.tzinfo is None:
            memory_time = memory_time.replace(
                tzinfo=timezone.utc
            )

        # 计算记忆距离现在的天数
        age_days = max(
            0.0,
            (
                datetime.now(timezone.utc)
                - memory_time
            ).total_seconds()
            / 86400,
        )

        # 时间越近，分数越接近1
        return 1.0 / (
            1.0 + age_days / 30.0
        )

    # 时间格式错误时返回中间值
    except (TypeError, ValueError):
        return 0.5



def retrieve_relevant_memories(
    vector_memories: list[StoredMemory | dict],
    query: str,
    embedding_model: SentenceTransformer,
    query_plan: MemoryQueryPlan | None = None,
    top_k: int = 3,
) -> list[str]:
    """
    使用结构化键和Embedding检索相关长期记忆。

    检索规则：

    1. memory_key精确匹配的记忆直接进入候选集；
    2. 没有精确匹配时，使用Embedding进行语义匹配；
    3. 最后结合重要性、可信度和时间新鲜度排序。
    """

    # 没有长期记忆时直接返回。
    if not vector_memories:
        return []

    # 如果查询规划器明确判断不需要长期记忆，
    # 就不进行任何检索。
    if (
        query_plan is not None
        and not query_plan.needs_memory
    ):
        return []

    # 优先使用查询规划器改写后的标准查询。
    #
    # 如果还没有传入query_plan，
    # 则使用玩家原始消息，兼容旧版main.py。
    if (
        query_plan is not None
        and query_plan.semantic_query.strip()
    ):
        semantic_query = query_plan.semantic_query.strip()
    else:
        semantic_query = query

    # 取出查询规划器生成的memory_key。
    #
    # 统一转换成小写并清理空格，
    # 避免大小写或空格造成匹配失败。
    planned_keys = {
        memory_key.strip().lower()
        for memory_key in (
            query_plan.memory_keys
            if query_plan is not None
            else []
        )
        if memory_key.strip()
    }

    # 将标准化查询转换成Embedding向量。
    query_embedding = embedding_model.encode(
        semantic_query,
        normalize_embeddings=True,
    )

    # 候选结构：
    #
    # 综合分数
    # 语义相似度
    # 是否精确匹配
    # 长期记忆对象
    scored_memories: list[
        tuple[float, float, bool, StoredMemory]
    ] = []

    # 遍历当前NPC的全部结构化长期记忆。
    for raw_memory in vector_memories:
        # load_vector_memory()当前可能返回：
        #
        # 1. StoredMemory对象；
        # 2. 从JSON读取出来的dict字典。
        #
        # 这里统一转换成StoredMemory对象，
        # 后续就可以稳定使用memory.embedding等属性。
        try:
            if isinstance(raw_memory, StoredMemory):
                memory = raw_memory
            else:
                memory = StoredMemory.model_validate(
                    raw_memory
                )

        except ValidationError as error:
            # 单条记忆格式错误时跳过，
            # 不让它导致整个检索过程失败。
            print(
                f"[跳过格式错误的长期记忆：{error}]"
            )
            continue

        # 没有Embedding的记忆无法进行语义检索。
        if not memory.embedding:
            continue

        # 标准化当前长期记忆的memory_key。
        stored_key = memory.memory_key.strip().lower()

        # 判断memory_key是否精确匹配。
        exact_key_match = (
            bool(stored_key)
            and stored_key in planned_keys
        )

        # 计算玩家问题和长期记忆的语义相似度。
        semantic_similarity = (
            _calculate_cosine_similarity(
                first_embedding=query_embedding,
                second_embedding=memory.embedding,
            )
        )

        # memory_key不匹配且语义相似度过低时，
        # 当前记忆与问题无关，不进入候选集。
        if (
            not exact_key_match
            and semantic_similarity < MIN_SIMILARITY
        ):
            continue

        # 根据更新时间计算记忆的新鲜度。
        recency_score = _calculate_recency_score(
            updated_at=memory.updated_at,
        )

        if exact_key_match:
            # memory_key精确匹配时，
            # 给予较高基础分，确保优先返回。
            final_score = (
                EXACT_KEY_BASE_SCORE
                + semantic_similarity
                * EXACT_SEMANTIC_WEIGHT
                + memory.importance
                * 0.05
                + memory.confidence
                * 0.10
                + recency_score
                * 0.10
            )
        else:
            # 没有精确匹配时，
            # 主要依赖语义相似度进行召回。
            final_score = (
                semantic_similarity
                * SEMANTIC_WEIGHT
                + memory.importance
                * IMPORTANCE_WEIGHT
                + memory.confidence
                * CONFIDENCE_WEIGHT
                + recency_score
                * RECENCY_WEIGHT
            )

        # 保存候选记忆及其各项分数。
        scored_memories.append(
            (
                final_score,
                semantic_similarity,
                exact_key_match,
                memory,
            )
        )

    # 先按综合分数排序。
    #
    # 综合分相同时：
    # memory_key精确匹配的排在前面，
    # 然后再比较语义相似度。
    scored_memories.sort(
        key=lambda item: (
            item[0],
            item[2],
            item[1],
        ),
        reverse=True,
    )

    # 只返回最相关的前top_k条记忆。
    selected_memories = scored_memories[:top_k]

    # 转换成可以直接放入LLM上下文的文字。
    formatted_memories: list[str] = []

    for (
        final_score,
        semantic_similarity,
        exact_key_match,
        memory,
    ) in selected_memories:
        # 显示当前记忆通过哪种方式被找到。
        match_type = (
            "memory_key精确匹配"
            if exact_key_match
            else "语义匹配"
        )

        formatted_memories.append(
            f"{memory.summary}"
            f"（记忆键：{memory.memory_key}；"
            f"匹配方式：{match_type}；"
            f"语义相似度：{semantic_similarity:.4f}；"
            f"综合分数：{final_score:.4f}）"
        )

    return formatted_memories

