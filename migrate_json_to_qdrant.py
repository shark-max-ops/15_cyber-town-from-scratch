"""
旧版JSON向量记忆迁移到Qdrant的工具。

功能说明：
- 自动查找所有NPC的旧版向量记忆JSON文件。
- 使用StoredMemory验证每条长期记忆。
- 复用JSON中已经存在的Embedding。
- 将有效长期记忆写入Qdrant。
- Embedding缺失或维度错误时重新生成。
- 保留原始JSON文件，不执行删除或修改。

主要变量含义：
- VECTOR_MEMORY_SUFFIX：旧向量记忆文件的固定后缀。
- DEFAULT_PLAYER_ID：旧记忆对应的默认玩家编号。
- EMBEDDING_MODEL_NAME：生成长期记忆向量的Embedding模型。
- vector_files：找到的全部旧向量记忆文件。
- npc_id：从文件名提取出的NPC编号。
- raw_memories：从JSON加载并验证后的记忆列表。
- memory：一条经过StoredMemory验证的长期记忆。
- vector_size：Qdrant集合要求的Embedding维度。
- migrated_count：成功写入Qdrant的记忆数量。
- regenerated_count：重新生成Embedding的记忆数量。
- skipped_count：因数据错误而跳过的记忆数量。
"""

from pathlib import Path

from pydantic import ValidationError
from sentence_transformers import SentenceTransformer

from memory import DATA_DIR, load_vector_memory
from memory_models import StoredMemory
from qdrant_memory_store import QdrantMemoryStore


# 旧向量记忆文件统一使用这个后缀。
VECTOR_MEMORY_SUFFIX = "_vector_memory.json"

# 当前项目尚未实现多玩家登录，
# 所以旧记忆统一属于默认玩家。
DEFAULT_PLAYER_ID = "default_player"

# 必须和项目当前使用的Embedding模型保持一致。
EMBEDDING_MODEL_NAME = "BAAI/bge-small-zh-v1.5"


def discover_npc_ids() -> list[str]:
    """从旧向量记忆文件名中发现全部NPC编号。"""

    # 搜索data目录下所有旧向量记忆文件。
    vector_files = sorted(
        DATA_DIR.glob(
            f"*{VECTOR_MEMORY_SUFFIX}"
        )
    )

    npc_ids: list[str] = []

    for vector_file in vector_files:
        # 示例：
        #
        # lin_zhou_vector_memory.json
        # ↓
        # lin_zhou
        npc_id = vector_file.name.removesuffix(
            VECTOR_MEMORY_SUFFIX
        )

        if npc_id:
            npc_ids.append(npc_id)

    return npc_ids


def migrate_npc_memories(
    *,
    npc_id: str,
    player_id: str,
    store: QdrantMemoryStore,
    embedding_model: SentenceTransformer,
    vector_size: int,
) -> dict[str, int]:
    """迁移一个NPC的全部有效长期记忆。"""

    statistics = {
        "loaded": 0,
        "migrated": 0,
        "regenerated": 0,
        "skipped": 0,
    }

    # 复用memory.py现有的加载函数。
    #
    # 该函数会使用StoredMemory过滤掉旧版或损坏记录。
    raw_memories = load_vector_memory(npc_id)

    statistics["loaded"] = len(raw_memories)

    for raw_memory in raw_memories:
        try:
            # 再次转换为StoredMemory对象，
            # 方便通过memory.summary等属性访问字段。
            memory = StoredMemory.model_validate(
                raw_memory
            )

            # 检查旧Embedding是否仍然符合当前模型维度。
            if len(memory.embedding) != vector_size:
                print(
                    f"[{npc_id}] 记忆"
                    f"{memory.memory_key}的向量维度异常，"
                    "正在重新生成Embedding"
                )

                # 使用记忆摘要重新生成标准化向量。
                regenerated_embedding = (
                    embedding_model.encode(
                        memory.summary,
                        normalize_embeddings=True,
                    )
                )

                memory.embedding = (
                    regenerated_embedding.tolist()
                )

                statistics["regenerated"] += 1

            # 把完整StoredMemory写入Qdrant。
            store.upsert_stored_memory(
                npc_id=npc_id,
                player_id=player_id,
                memory=memory,
            )

            statistics["migrated"] += 1

        except (
            ValidationError,
            TypeError,
            ValueError,
        ) as error:
            # 单条记录出错时只跳过当前记录，
            # 不让一条坏数据中断整个迁移过程。
            statistics["skipped"] += 1

            print(
                f"[{npc_id}] 跳过一条无效记忆："
                f"{error}"
            )

    return statistics


def main() -> None:
    """执行全部NPC的长期记忆迁移。"""

    print("=" * 60)
    print("开始迁移JSON长期记忆到Qdrant")
    print("=" * 60)

    # 自动发现拥有旧向量记忆文件的NPC。
    npc_ids = discover_npc_ids()

    if not npc_ids:
        print("没有找到旧版向量记忆文件。")
        return

    print(
        f"发现{len(npc_ids)}个NPC："
        f"{', '.join(npc_ids)}"
    )

    print(
        f"正在加载Embedding模型："
        f"{EMBEDDING_MODEL_NAME}"
    )

    # 加载与原项目相同的BGE模型。
    embedding_model = SentenceTransformer(
        EMBEDDING_MODEL_NAME
    )

    # 从当前Sentence Transformers模型读取真实向量维度。
    #
    # 新版本已经将get_sentence_embedding_dimension()
    # 更名为get_embedding_dimension()。
    vector_size = (
        embedding_model
        .get_embedding_dimension()
    )

    if vector_size is None:
        raise ValueError(
            "无法获取Embedding模型的向量维度"
        )

    print(f"Embedding向量维度：{vector_size}")

    # 整个迁移过程只创建一个Qdrant客户端。
    store = QdrantMemoryStore(
        vector_size=vector_size
    )

    total_loaded = 0
    total_migrated = 0
    total_regenerated = 0
    total_skipped = 0

    try:
        # 逐个迁移NPC，确保记忆仍然以npc_id隔离。
        for npc_id in npc_ids:
            print("-" * 60)
            print(f"正在迁移NPC：{npc_id}")

            statistics = migrate_npc_memories(
                npc_id=npc_id,
                player_id=DEFAULT_PLAYER_ID,
                store=store,
                embedding_model=embedding_model,
                vector_size=vector_size,
            )

            total_loaded += statistics["loaded"]
            total_migrated += statistics["migrated"]
            total_regenerated += statistics[
                "regenerated"
            ]
            total_skipped += statistics["skipped"]

            print(
                f"[{npc_id}] "
                f"读取{statistics['loaded']}条，"
                f"写入{statistics['migrated']}条，"
                f"重建向量{statistics['regenerated']}条，"
                f"跳过{statistics['skipped']}条"
            )

        print("=" * 60)
        print("迁移完成")
        print(f"JSON有效记忆：{total_loaded}条")
        print(f"Qdrant写入操作：{total_migrated}条")
        print(f"重新生成向量：{total_regenerated}条")
        print(f"跳过无效记录：{total_skipped}条")
        print(
            f"Qdrant当前记忆总数："
            f"{store.count_memories()}条"
        )
        print("原始JSON文件已保留，没有删除。")
        print("=" * 60)

    finally:
        # 即使迁移中发生异常，也要关闭数据库客户端。
        store.close()


if __name__ == "__main__":
    main()