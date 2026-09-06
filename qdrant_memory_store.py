"""
Qdrant长期记忆存储模块。

功能说明：
- 创建本地持久化Qdrant客户端。
- 自动创建长期记忆集合。
- 将NPC长期记忆及其Embedding写入Qdrant。
- 为相同玩家、NPC和memory_key生成固定Point ID。
- 统计Qdrant中保存的长期记忆数量。

主要变量含义：
- storage_path：Qdrant本地数据库目录。
- collection_name：保存长期记忆的集合名称。
- vector_size：Embedding向量维度。
- client：Qdrant客户端。
- npc_id：拥有该记忆的NPC编号。
- player_id：该记忆对应的玩家编号。
- memory_key：结构化记忆键。
- embedding：记忆文本对应的向量。
- payload：与向量一起保存的记忆属性。
- point_id：Qdrant中一条记忆的唯一编号。
- existing_memory：通过memory_key找到的已有记忆。
- duplicate_memory：通过Embedding找到的语义重复记忆。
- scroll_offset：Qdrant分批读取数据时的分页位置。
- batch_size：每次从Qdrant读取的记忆数量。
"""

from datetime import datetime, timezone
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchAny,
    MatchValue,
    PointIdsList,
    PointStruct,
    VectorParams,
)

from config import QDRANT_COLLECTION_NAME, QDRANT_PATH
from typing import Any
from memory_models import StoredMemory

class QdrantMemoryStore:
    """管理Qdrant中的NPC长期记忆。"""

    def __init__(
        self,
        vector_size: int,
        storage_path: Path = QDRANT_PATH,
        collection_name: str = QDRANT_COLLECTION_NAME,
    ) -> None:
        """创建Qdrant客户端并确保长期记忆集合存在。"""

        if vector_size <= 0:
            raise ValueError("vector_size必须大于0")

        self.storage_path = Path(storage_path)
        self.collection_name = collection_name
        self.vector_size = vector_size

        self.storage_path.mkdir(parents=True, exist_ok=True)

        self.client = QdrantClient(
            path=str(self.storage_path),
        )

        self._ensure_collection()

    def _ensure_collection(self) -> None:
        """确保长期记忆集合存在。"""

        if self.client.collection_exists(self.collection_name):
            print(f"Qdrant集合已存在：{self.collection_name}")
            return

        self.client.create_collection(
            collection_name=self.collection_name,
            vectors_config=VectorParams(
                size=self.vector_size,
                distance=Distance.COSINE,
            ),
        )

        print(
            f"Qdrant集合创建成功：{self.collection_name}，"
            f"向量维度：{self.vector_size}"
        )

    @staticmethod
    def _build_point_id(
        npc_id: str,
        player_id: str,
        memory_key: str,
    ) -> str:
        """根据NPC、玩家和记忆键生成固定UUID。"""

        unique_text = (
            f"cyber-town:{npc_id}:{player_id}:{memory_key}"
        )

        return str(uuid5(NAMESPACE_URL, unique_text))

    def upsert_memory(
        self,
        *,
        npc_id: str,
        player_id: str,
        memory_key: str,
        memory_type: str,
        value: str,
        summary: str,
        embedding: list[float],
        importance: float,
        confidence: float,
        sensitive: bool = False,
        source: str = "player_statement",
        source_text: str = "",
        memory_id: str = "",
        created_at: datetime | str | None = None,
        updated_at: datetime | str | None = None,
    ) -> str:
        """
        新增或更新一条长期记忆。

        相同NPC、玩家和memory_key会生成相同的Qdrant Point ID，
        因此再次写入时会覆盖旧值，实现UPDATE效果。
        """

        # NPC编号用于隔离不同NPC的记忆。
        if not npc_id.strip():
            raise ValueError("npc_id不能为空")

        # 玩家编号用于隔离不同玩家的记忆。
        if not player_id.strip():
            raise ValueError("player_id不能为空")

        # memory_key用于判断两条记忆是否属于同一属性。
        if not memory_key.strip():
            raise ValueError("memory_key不能为空")

        # Qdrant集合中的所有向量必须具有相同维度。
        if len(embedding) != self.vector_size:
            raise ValueError(
                f"Embedding维度错误：期望{self.vector_size}，"
                f"实际{len(embedding)}"
            )

        # 根据NPC、玩家和记忆键生成稳定的Qdrant编号。
        #
        # 例如player.favorite_food发生变化时，
        # 新值会覆盖旧值，不会产生互相冲突的重复记录。
        point_id = self._build_point_id(
            npc_id=npc_id,
            player_id=player_id,
            memory_key=memory_key,
        )

        # 当前UTC时间作为缺省时间。
        current_time = datetime.now(
            timezone.utc
        ).isoformat()

        # datetime对象需要转换为JSON可以保存的ISO字符串。
        if isinstance(created_at, datetime):
            created_at_text = created_at.isoformat()
        elif isinstance(created_at, str) and created_at.strip():
            created_at_text = created_at
        else:
            created_at_text = current_time

        if isinstance(updated_at, datetime):
            updated_at_text = updated_at.isoformat()
        elif isinstance(updated_at, str) and updated_at.strip():
            updated_at_text = updated_at
        else:
            updated_at_text = current_time

        # 如果没有传入原始memory_id，
        # 就使用Qdrant的point_id作为记忆编号。
        final_memory_id = (
            memory_id.strip()
            if memory_id.strip()
            else point_id
        )

        # payload保存向量之外的结构化记忆信息。
        #
        # 后续可以使用npc_id、player_id和memory_key过滤，
        # 不需要把所有记忆都取回Python再逐条检查。
        payload = {
            "memory_id": final_memory_id,
            "npc_id": npc_id,
            "player_id": player_id,
            "memory_key": memory_key,
            "memory_type": memory_type,
            "value": value,
            "summary": summary,
            "importance": importance,
            "confidence": confidence,
            "sensitive": sensitive,
            "source": source,
            "source_text": source_text,
            "created_at": created_at_text,
            "updated_at": updated_at_text,
        }

        # Point由唯一编号、向量和payload三部分组成。
        point = PointStruct(
            id=point_id,
            vector=embedding,
            payload=payload,
        )

        # upsert表示：
        #
        # Point ID不存在 → 新增；
        # Point ID已存在   → 更新。
        self.client.upsert(
            collection_name=self.collection_name,
            points=[point],
            wait=True,
        )

        return point_id

    def upsert_stored_memory(
        self,
        *,
        npc_id: str,
        player_id: str,
        memory: StoredMemory,
    ) -> str:
        """将现有StoredMemory对象写入Qdrant。"""

        # StoredMemory已经经过Pydantic验证，
        # 可以把它的字段直接交给统一的upsert_memory()。
        return self.upsert_memory(
            npc_id=npc_id,
            player_id=player_id,
            memory_id=memory.memory_id,
            memory_key=memory.memory_key,
            memory_type=memory.memory_type,
            value=memory.value,
            summary=memory.summary,
            embedding=memory.embedding,
            importance=memory.importance,
            confidence=memory.confidence,
            sensitive=False,
            source=memory.source,
            source_text=memory.source_text,
            created_at=memory.created_at,
            updated_at=memory.updated_at,
        )

    def delete_memory(
        self,
        *,
        npc_id: str,
        player_id: str,
        memory_key: str,
    ) -> str:
        """按照NPC、玩家和memory_key删除一条长期记忆。"""

        if not npc_id.strip():
            raise ValueError("npc_id不能为空")

        if not player_id.strip():
            raise ValueError("player_id不能为空")

        if not memory_key.strip():
            raise ValueError("memory_key不能为空")

        # 写入时使用NPC、玩家和memory_key生成固定Point ID，
        # 所以删除时使用相同规则就能定位原记录。
        point_id = self._build_point_id(
            npc_id=npc_id,
            player_id=player_id,
            memory_key=memory_key,
        )

        # PointIdsList告诉Qdrant：
        # 本次操作按照Point ID删除指定记录。
        self.client.delete(
            collection_name=self.collection_name,
            points_selector=PointIdsList(
                points=[point_id]
            ),
            wait=True,
        )

        return point_id

    @staticmethod
    def _build_owner_filter(
        npc_id: str,
        player_id: str,
    ) -> Filter:
        """创建NPC和玩家过滤条件。"""

        return Filter(
            must=[
                FieldCondition(
                    key="npc_id",
                    match=MatchValue(value=npc_id),
                ),
                FieldCondition(
                    key="player_id",
                    match=MatchValue(value=player_id),
                ),
            ]
        )

    @staticmethod
    def _point_to_dict(
        point,
        retrieval_source: str,
        similarity: float | None = None,
    ) -> dict[str, Any]:
        """将Qdrant查询结果转换为普通字典。"""

        memory = dict(point.payload or {})

        memory["point_id"] = str(point.id)
        memory["retrieval_source"] = retrieval_source
        memory["similarity"] = similarity

        return memory

    def search_by_keys(
        self,
        *,
        npc_id: str,
        player_id: str,
        memory_keys: list[str],
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """按照memory_key精确查询长期记忆。"""

        cleaned_keys = [
            key.strip()
            for key in memory_keys
            if key.strip()
        ]

        if not cleaned_keys:
            return []

        query_filter = Filter(
            must=[
                FieldCondition(
                    key="npc_id",
                    match=MatchValue(value=npc_id),
                ),
                FieldCondition(
                    key="player_id",
                    match=MatchValue(value=player_id),
                ),
                FieldCondition(
                    key="memory_key",
                    match=MatchAny(any=cleaned_keys),
                ),
            ]
        )

        records, _next_page = self.client.scroll(
            collection_name=self.collection_name,
            scroll_filter=query_filter,
            limit=limit,
            with_payload=True,
            with_vectors=False,
        )

        return [
            self._point_to_dict(
                point=record,
                retrieval_source="exact",
            )
            for record in records
        ]


    def get_memory_by_key(
        self,
        *,
        npc_id: str,
        player_id: str,
        memory_key: str,
    ) -> dict[str, Any] | None:
        """通过memory_key读取一条长期记忆。"""

        cleaned_key = memory_key.strip().lower()

        if not cleaned_key:
            return None

        # 复用现有精确查询方法。
        memories = self.search_by_keys(
            npc_id=npc_id,
            player_id=player_id,
            memory_keys=[cleaned_key],
            limit=1,
        )

        if not memories:
            return None

        return memories[0]


    def find_semantic_duplicate(
        self,
        *,
        npc_id: str,
        player_id: str,
        memory_type: str,
        embedding: list[float],
        similarity_threshold: float = 0.97,
    ) -> dict[str, Any] | None:
        """查找类型相同且语义高度相似的长期记忆。"""

        if len(embedding) != self.vector_size:
            raise ValueError(
                f"Embedding维度错误：期望{self.vector_size}，"
                f"实际{len(embedding)}"
            )

        # 重复检查必须同时限制：
        #
        # 1. 当前NPC；
        # 2. 当前玩家；
        # 3. 相同记忆类型。
        #
        # 否则“喜欢葡挞”和“讨厌葡挞”
        # 可能因为文本接近而被错误地当成同一记忆。
        duplicate_filter = Filter(
            must=[
                FieldCondition(
                    key="npc_id",
                    match=MatchValue(value=npc_id),
                ),
                FieldCondition(
                    key="player_id",
                    match=MatchValue(value=player_id),
                ),
                FieldCondition(
                    key="memory_type",
                    match=MatchValue(
                        value=memory_type
                    ),
                ),
            ]
        )

        # 只需要最相似的一条记录。
        result = self.client.query_points(
            collection_name=self.collection_name,
            query=embedding,
            query_filter=duplicate_filter,
            limit=1,
            score_threshold=similarity_threshold,
            with_payload=True,
            with_vectors=False,
        )

        if not result.points:
            return None

        duplicate_point = result.points[0]

        return self._point_to_dict(
            point=duplicate_point,
            retrieval_source="duplicate",
            similarity=float(
                duplicate_point.score
            ),
        )

    def list_memories(
        self,
        *,
        npc_id: str,
        player_id: str,
        batch_size: int = 100,
        include_embeddings: bool = False,
    ) -> list[dict[str, Any]]:
        """
        读取指定NPC与玩家的全部长期记忆。

        include_embeddings=False：
        只返回payload，适合普通信息查看。

        include_embeddings=True：
        同时返回向量，适合备份到旧版JSON。
        """

        if batch_size <= 0:
            raise ValueError(
                "batch_size必须大于0"
            )

        all_memories: list[
            dict[str, Any]
        ] = []

        # 第一次查询没有分页位置。
        scroll_offset = None

        # 限制只能读取指定NPC和玩家的记忆。
        owner_filter = self._build_owner_filter(
            npc_id=npc_id,
            player_id=player_id,
        )

        while True:
            records, next_offset = (
                self.client.scroll(
                    collection_name=(
                        self.collection_name
                    ),
                    scroll_filter=owner_filter,
                    limit=batch_size,
                    offset=scroll_offset,
                    with_payload=True,
                    # 导出JSON备份时需要同时读取向量。
                    with_vectors=include_embeddings,
                )
            )

            for record in records:
                memory = self._point_to_dict(
                    point=record,
                    retrieval_source="list",
                )

                # Qdrant把向量和payload分开保存。
                #
                # 旧JSON的StoredMemory则要求embedding
                # 直接位于记忆字典中，因此这里重新合并。
                if include_embeddings:
                    record_vector = record.vector

                    if isinstance(
                        record_vector,
                        list,
                    ):
                        memory["embedding"] = [
                            float(value)
                            for value
                            in record_vector
                        ]
                    else:
                        # 当前集合只使用一个普通向量，
                        # 正常情况下不会进入这里。
                        memory["embedding"] = []

                all_memories.append(memory)

            if next_offset is None:
                break

            scroll_offset = next_offset

        return all_memories


    def semantic_search(
        self,
        *,
        npc_id: str,
        player_id: str,
        query_embedding: list[float],
        limit: int = 5,
        score_threshold: float = 0.45,
    ) -> list[dict[str, Any]]:
        """使用Embedding语义检索长期记忆。"""

        if len(query_embedding) != self.vector_size:
            raise ValueError(
                f"查询Embedding维度错误：期望{self.vector_size}，"
                f"实际{len(query_embedding)}"
            )

        result = self.client.query_points(
            collection_name=self.collection_name,
            query=query_embedding,
            query_filter=self._build_owner_filter(
                npc_id=npc_id,
                player_id=player_id,
            ),
            limit=limit,
            score_threshold=score_threshold,
            with_payload=True,
            with_vectors=False,
        )

        return [
            self._point_to_dict(
                point=point,
                retrieval_source="semantic",
                similarity=float(point.score),
            )
            for point in result.points
        ]

    def retrieve_memories(
        self,
        *,
        npc_id: str,
        player_id: str,
        memory_keys: list[str],
        query_embedding: list[float] | None,
        top_k: int = 3,
        score_threshold: float = 0.45,
    ) -> list[dict[str, Any]]:
        """综合memory_key精确匹配和Embedding语义检索。"""

        exact_memories = self.search_by_keys(
            npc_id=npc_id,
            player_id=player_id,
            memory_keys=memory_keys,
            limit=max(top_k, len(memory_keys)),
        )

        semantic_memories: list[dict[str, Any]] = []

        if query_embedding is not None:
            semantic_memories = self.semantic_search(
                npc_id=npc_id,
                player_id=player_id,
                query_embedding=query_embedding,
                limit=max(top_k * 2, 5),
                score_threshold=score_threshold,
            )

        # 使用point_id去重
        merged_memories: dict[str, dict[str, Any]] = {}

        for memory in exact_memories:
            merged_memories[memory["point_id"]] = memory

        for memory in semantic_memories:
            point_id = memory["point_id"]

            if point_id in merged_memories:
                # 同时被精确检索和语义检索命中
                merged_memories[point_id]["retrieval_source"] = (
                    "exact+semantic"
                )
                merged_memories[point_id]["similarity"] = memory[
                    "similarity"
                ]
            else:
                merged_memories[point_id] = memory

        memories = list(merged_memories.values())

        def ranking_key(
            memory: dict[str, Any],
        ) -> tuple[int, float, float, float]:
            """计算综合排序依据。"""

            source = str(memory.get("retrieval_source", ""))
            exact_priority = 1 if "exact" in source else 0

            similarity = float(memory.get("similarity") or 0.0)
            importance = float(memory.get("importance") or 0.0)
            confidence = float(memory.get("confidence") or 0.0)

            return (
                exact_priority,
                similarity,
                importance,
                confidence,
            )

        memories.sort(
            key=ranking_key,
            reverse=True,
        )

        return memories[:top_k]


    def count_memories(self) -> int:
        """统计Qdrant集合中的长期记忆数量。"""

        result = self.client.count(
            collection_name=self.collection_name,
            exact=True,
        )

        return result.count

    def get_collection_info(self):
        """获取长期记忆集合的信息。"""

        return self.client.get_collection(
            collection_name=self.collection_name,
        )

    def close(self) -> None:
        """关闭Qdrant客户端。"""

        self.client.close()