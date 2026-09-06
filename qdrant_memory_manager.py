"""
Qdrant结构化长期记忆管理模块。

功能说明：
- 执行DeepSeek提取出的REMEMBER、FORGET和NONE操作。
- 使用memory_key判断已有记忆。
- 使用Embedding判断语义重复记忆。
- 将新增或更新后的记忆写入Qdrant。
- 将Qdrant中的长期记忆同步到旧版JSON作为备份。
- 保证不同NPC和不同玩家的长期记忆相互隔离。

主要变量含义：
- store：Qdrant底层存储对象。
- embedding_model：生成记忆向量的Embedding模型。
- npc_id：拥有当前记忆的NPC编号。
- player_id：当前玩家编号。
- extraction_result：DeepSeek生成的结构化记忆操作。
- candidate：一条待处理的候选记忆。
- existing_memory：memory_key相同的已有记忆。
- duplicate_memory：语义高度相似的已有记忆。
- stored_memory：最终准备写入Qdrant的正式记忆。
- memory_changed：Qdrant记忆是否发生变化。
- statistics：本轮记忆新增、更新、删除等统计。
- backup_memories：从Qdrant导出并写回JSON的备份记录。
- MIN_CONFIDENCE：允许保存候选记忆的最低置信度。
- MIN_IMPORTANCE：允许保存候选记忆的最低重要度。
- DUPLICATE_SIMILARITY：判断语义重复记忆的相似度阈值。
"""

from datetime import datetime, timezone
from uuid import uuid4

from pydantic import ValidationError
from sentence_transformers import SentenceTransformer

from memory import save_vector_memory
from memory_models import (
    MemoryExtractionResult,
    StoredMemory,
)
from qdrant_memory_store import QdrantMemoryStore
# 候选记忆允许保存的最低置信度。
#
# 低于该值说明DeepSeek对提取结果把握不足，
# 不应该直接写入长期记忆。
MIN_CONFIDENCE = 0.70

# 候选记忆允许保存的最低重要度。
#
# 过于临时或无关的信息不需要长期保存。
MIN_IMPORTANCE = 0.35

# 判断两条同类型记忆是否语义重复的相似度。
#
# 该值较高，避免把仅仅相关但含义不同的事实合并。
DUPLICATE_SIMILARITY = 0.97

class QdrantMemoryManager:
    """使用Qdrant管理结构化长期记忆。"""

    def __init__(
        self,
        *,
        store: QdrantMemoryStore,
        embedding_model: SentenceTransformer,
    ) -> None:
        """保存Qdrant存储器和Embedding模型。"""

        self.store = store
        self.embedding_model = embedding_model

    def apply_extraction(
        self,
        *,
        npc_id: str,
        player_id: str,
        extraction_result: MemoryExtractionResult,
    ) -> dict[str, int]:
        """执行一次完整的长期记忆处理。"""

        statistics = {
            "added": 0,
            "updated": 0,
            "deleted": 0,
            "skipped": 0,
            "qdrant_written": 0,
            "qdrant_deleted": 0,
            "qdrant_failed": 0,
            "backup_failed": 0,
        }

        # 只有Qdrant内容发生变化时，
        # 才重新生成JSON备份。
        memory_changed = False

        for candidate in extraction_result.memories:
            # NONE表示没有需要执行的记忆操作。
            if candidate.action == "NONE":
                statistics["skipped"] += 1
                continue

            # 所有正式操作都必须具有memory_key。
            if not candidate.memory_key.strip():
                statistics["skipped"] += 1
                continue

            # 统一清理memory_key首尾空格并转成小写。
            #
            # 例如Player.Name和player.name
            # 应被视为同一个结构化记忆键。
            memory_key = (
                candidate.memory_key
                .strip()
                .lower()
            )

            # ==================================================
            # FORGET：删除长期记忆
            # ==================================================
            if candidate.action == "FORGET":
                try:
                    # 删除前先检查记忆是否存在，
                    # 方便准确统计实际删除数量。
                    existing_memory = (
                        self.store.get_memory_by_key(
                            npc_id=npc_id,
                            player_id=player_id,
                            memory_key=memory_key,
                        )
                    )

                    # 即使没有找到记录也可以执行删除，
                    # Qdrant删除不存在的Point不会破坏数据库。
                    self.store.delete_memory(
                        npc_id=npc_id,
                        player_id=player_id,
                        memory_key=memory_key,
                    )

                    if existing_memory is not None:
                        statistics["deleted"] += 1
                        statistics[
                            "qdrant_deleted"
                        ] += 1
                        memory_changed = True
                    else:
                        statistics["skipped"] += 1

                except Exception as error:
                    statistics["qdrant_failed"] += 1

                    print(
                        "[Qdrant删除记忆失败] "
                        f"NPC={npc_id}，"
                        f"玩家={player_id}，"
                        f"记忆键={memory_key}，"
                        f"错误={error}"
                    )

                continue

            # ==================================================
            # REMEMBER：检查候选记忆质量
            # ==================================================

            # 敏感信息只禁止保存，不影响FORGET。
            #
            # 因此该判断特意放在FORGET处理之后，
            # 玩家依然可以要求系统删除敏感记忆。
            if candidate.sensitive:
                print(
                    "[记忆安全] 检测到敏感信息，"
                    "本条内容不会保存"
                )

                statistics["skipped"] += 1
                continue

            if candidate.confidence < MIN_CONFIDENCE:
                statistics["skipped"] += 1
                continue

            if candidate.importance < MIN_IMPORTANCE:
                statistics["skipped"] += 1
                continue

            if (
                not candidate.value.strip()
                or not candidate.summary.strip()
            ):
                statistics["skipped"] += 1
                continue

            # 为标准化记忆摘要生成向量。
            embedding_array = (
                self.embedding_model.encode(
                    candidate.summary,
                    normalize_embeddings=True,
                )
            )

            embedding = embedding_array.tolist()

            try:
                # 第一优先级：
                # 使用memory_key查找同一属性。
                existing_memory = (
                    self.store.get_memory_by_key(
                        npc_id=npc_id,
                        player_id=player_id,
                        memory_key=memory_key,
                    )
                )

                # 第二优先级：
                # memory_key没命中时检查语义重复。
                if existing_memory is None:
                    duplicate_memory = (
                        self.store
                        .find_semantic_duplicate(
                            npc_id=npc_id,
                            player_id=player_id,
                            memory_type=(
                                candidate.memory_type
                            ),
                            embedding=embedding,
                            similarity_threshold=(
                                DUPLICATE_SIMILARITY
                            ),
                        )
                    )

                    existing_memory = (
                        duplicate_memory
                    )

                # 获取当前UTC时间。
                current_time = datetime.now(
                    timezone.utc
                )

                # ==================================================
                # UPDATE：更新已有长期记忆
                # ==================================================
                if existing_memory is not None:
                    old_value = str(
                        existing_memory.get(
                            "value",
                            "",
                        )
                    )

                    old_summary = str(
                        existing_memory.get(
                            "summary",
                            "",
                        )
                    )

                    # 内容完全相同时不用重复写入。
                    if (
                        old_value == candidate.value
                        and old_summary
                        == candidate.summary
                    ):
                        statistics["skipped"] += 1
                        continue

                    old_memory_key = str(
                        existing_memory.get(
                            "memory_key",
                            memory_key,
                        )
                    )

                    # 更新时保留旧memory_id和创建时间。
                    stored_memory = StoredMemory(
                        memory_id=str(
                            existing_memory.get(
                                "memory_id",
                                uuid4(),
                            )
                        ),
                        memory_type=(
                            candidate.memory_type
                        ),
                        memory_key=memory_key,
                        value=candidate.value,
                        summary=candidate.summary,
                        importance=(
                            candidate.importance
                        ),
                        confidence=(
                            candidate.confidence
                        ),
                        source="player_statement",
                        source_text=(
                            candidate.source_text
                        ),
                        created_at=(
                            existing_memory.get(
                                "created_at",
                                current_time,
                            )
                        ),
                        updated_at=current_time,
                        embedding=embedding,
                    )

                    # 先写入新记录，再清理可能存在的旧key。
                    #
                    # 这个顺序可以避免新记录写入失败时，
                    # 旧记忆已经被提前删除。
                    self.store.upsert_stored_memory(
                        npc_id=npc_id,
                        player_id=player_id,
                        memory=stored_memory,
                    )

                    statistics["updated"] += 1
                    statistics[
                        "qdrant_written"
                    ] += 1
                    memory_changed = True

                    # 语义重复记录可能使用了不同的memory_key。
                    #
                    # 新记录写入成功后，删除旧key对应的Point，
                    # 防止数据库中同时保留两条重复事实。
                    if old_memory_key != memory_key:
                        self.store.delete_memory(
                            npc_id=npc_id,
                            player_id=player_id,
                            memory_key=(
                                old_memory_key
                            ),
                        )

                        statistics[
                            "qdrant_deleted"
                        ] += 1

                # ==================================================
                # ADD：创建全新长期记忆
                # ==================================================
                else:
                    stored_memory = StoredMemory(
                        memory_id=str(uuid4()),
                        memory_type=(
                            candidate.memory_type
                        ),
                        memory_key=memory_key,
                        value=candidate.value,
                        summary=candidate.summary,
                        importance=(
                            candidate.importance
                        ),
                        confidence=(
                            candidate.confidence
                        ),
                        source="player_statement",
                        source_text=(
                            candidate.source_text
                        ),
                        created_at=current_time,
                        updated_at=current_time,
                        embedding=embedding,
                    )

                    self.store.upsert_stored_memory(
                        npc_id=npc_id,
                        player_id=player_id,
                        memory=stored_memory,
                    )

                    statistics["added"] += 1
                    statistics[
                        "qdrant_written"
                    ] += 1
                    memory_changed = True

            except Exception as error:
                # Qdrant现在是正式长期记忆主存储。
                #
                # 单条记忆失败时不影响NPC回复，
                # 但不会把失败操作写入JSON备份。
                statistics["qdrant_failed"] += 1

                print(
                    "[Qdrant长期记忆处理失败] "
                    f"NPC={npc_id}，"
                    f"玩家={player_id}，"
                    f"记忆键={memory_key}，"
                    f"错误={error}"
                )

        # Qdrant发生变化后重新生成JSON备份。
        if memory_changed:
            try:
                self._sync_json_backup(
                    npc_id=npc_id,
                    player_id=player_id,
                )

            except Exception as error:
                # JSON现在只是备份。
                #
                # 备份失败不能撤销已经成功写入Qdrant的记忆。
                statistics["backup_failed"] += 1

                print(
                    "[长期记忆JSON备份失败] "
                    f"NPC={npc_id}，"
                    f"玩家={player_id}，"
                    f"错误={error}"
                )

        return statistics

    def _sync_json_backup(
        self,
        *,
        npc_id: str,
        player_id: str,
    ) -> None:
        """把Qdrant长期记忆导出为旧版JSON备份。"""

        # 导出时必须包含Embedding，
        # 才能继续符合StoredMemory的数据结构。
        qdrant_memories = self.store.list_memories(
            npc_id=npc_id,
            player_id=player_id,
            include_embeddings=True,
        )

        backup_memories: list[dict] = []

        for raw_memory in qdrant_memories:
            try:
                # 只选择StoredMemory真正需要的字段。
                #
                # npc_id、player_id、point_id、
                # retrieval_source等Qdrant专用字段
                # 不写入旧版JSON。
                stored_memory = StoredMemory(
                    memory_id=str(
                        raw_memory["memory_id"]
                    ),
                    memory_type=str(
                        raw_memory["memory_type"]
                    ),
                    memory_key=str(
                        raw_memory["memory_key"]
                    ),
                    value=str(
                        raw_memory["value"]
                    ),
                    summary=str(
                        raw_memory["summary"]
                    ),
                    importance=float(
                        raw_memory["importance"]
                    ),
                    confidence=float(
                        raw_memory["confidence"]
                    ),
                    source=str(
                        raw_memory.get(
                            "source",
                            "player_statement",
                        )
                    ),
                    source_text=str(
                        raw_memory.get(
                            "source_text",
                            "",
                        )
                    ),
                    created_at=(
                        raw_memory["created_at"]
                    ),
                    updated_at=(
                        raw_memory["updated_at"]
                    ),
                    embedding=list(
                        raw_memory["embedding"]
                    ),
                )

                backup_memories.append(
                    stored_memory.model_dump(
                        mode="json"
                    )
                )

            except (
                KeyError,
                TypeError,
                ValueError,
                ValidationError,
            ) as error:
                # 单条异常数据不应该阻止其他记忆备份。
                print(
                    "[跳过无法备份的Qdrant记忆] "
                    f"NPC={npc_id}，"
                    f"错误={error}"
                )

        # 覆盖当前NPC旧版向量JSON，
        # 使它成为Qdrant当前状态的可读备份。
        save_vector_memory(
            npc_id=npc_id,
            vector_memories=backup_memories,
        )