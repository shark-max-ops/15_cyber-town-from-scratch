"""
赛博小镇应用组件初始化模块。

功能说明：
统一创建和保存赛博小镇运行需要的全部核心组件，
包括DeepSeek客户端、Embedding模型、NPC管理器、
长期记忆系统、好感度系统、状态管理器和日志系统。

终端程序和FastAPI后端都可以使用同一个ApplicationContext，
避免在多个文件中重复编写初始化代码。

主要变量含义：
- initialized：全部应用组件是否已经初始化完成。
- initialization_lock：防止多个请求同时重复初始化组件。
- base_url：DeepSeek API地址。
- model：当前使用的大语言模型名称。
- client：DeepSeek API客户端。
- embedding_model：长期记忆使用的Embedding模型。
- memory_extractor：长期记忆写入提取器。
- memory_query_planner：长期记忆查询规划器。
- affinity_analyzer：玩家态度和好感度分析器。
- relationship_manager：NPC好感度管理器。
- npc_manager：全部NPC对象的管理器。
- state_manager：NPC运行状态管理器。
- dialogue_logger：对话和错误日志记录器。
- batch_dialogue_generator：批量背景对话生成器。
- background_cache：背景对话缓存管理器。
- application_context：供整个项目共用的应用组件容器实例。
- qdrant_store：Qdrant长期记忆向量存储器。
- qdrant_store：Qdrant长期记忆底层存储器。
- qdrant_memory_manager：Qdrant长期记忆业务管理器。
"""

from threading import RLock

from openai import OpenAI
from sentence_transformers import SentenceTransformer

from affinity_analyzer import AffinityAnalyzer
from agents import NPCAgentManager
from background_cache import BackgroundDialogueCache
from batch_dialogue import BatchDialogueGenerator
from config import load_config
from dialogue_logger import DialogueLogger
from memory_extractor import MemoryExtractor
from memory_query_planner import MemoryQueryPlanner
from relationship_manager import RelationshipManager
from state_manager import StateManager
from qdrant_memory_store import QdrantMemoryStore

from qdrant_memory_manager import QdrantMemoryManager
from qdrant_memory_store import QdrantMemoryStore

# 长期记忆使用的中文Embedding模型。
EMBEDDING_MODEL_NAME = "BAAI/bge-small-zh-v1.5"

# 背景对话缓存有效期。
BACKGROUND_CACHE_TTL_SECONDS = 300


class ApplicationContext:
    """赛博小镇全部核心组件的统一容器。"""

    def __init__(self) -> None:
        """创建尚未初始化的应用容器。"""

        # 初始状态下组件尚未创建。
        self.initialized = False

        # 防止FastAPI并发启动时重复初始化。
        self.initialization_lock = RLock()

        # 以下属性会在initialize()中完成赋值。
        self.base_url: str
        self.model: str
        self.client: OpenAI
        self.embedding_model: SentenceTransformer
        # 整个后端共用同一个Qdrant客户端。
        #
        # 不应该在每次对话时重新创建，
        # 否则本地Qdrant可能出现重复连接或文件锁问题。
        self.qdrant_store: QdrantMemoryStore
        # 负责长期记忆新增、更新、遗忘和JSON备份。
        self.qdrant_memory_manager: (
            QdrantMemoryManager
        )
        self.memory_extractor: MemoryExtractor
        self.memory_query_planner: MemoryQueryPlanner
        self.affinity_analyzer: AffinityAnalyzer
        self.relationship_manager: RelationshipManager
        self.npc_manager: NPCAgentManager
        self.state_manager: StateManager
        self.dialogue_logger: DialogueLogger
        self.batch_dialogue_generator: BatchDialogueGenerator
        self.background_cache: BackgroundDialogueCache

    def initialize(self) -> None:
        """初始化赛博小镇全部核心组件。"""

        # 所有初始化操作都由同一把锁保护。
        with self.initialization_lock:
            # 已初始化时直接返回，
            # 避免重复加载Embedding模型和NPC。
            if self.initialized:
                return

            # 读取.env中的DeepSeek配置。
            api_key, base_url, model = load_config()

            self.base_url = base_url
            self.model = model

            print("配置读取成功")
            print(f"API地址：{self.base_url}")
            print(f"模型名称：{self.model}")
            print("API密钥：已读取，不显示具体内容")

            # 创建DeepSeek API客户端。
            self.client = OpenAI(
                api_key=api_key,
                base_url=self.base_url,
            )

            print("LLM客户端创建成功")

            # 加载中文Embedding模型。
            print(
                f"正在加载Embedding模型："
                f"{EMBEDDING_MODEL_NAME}"
            )

            self.embedding_model = SentenceTransformer(
                EMBEDDING_MODEL_NAME,
            )

            print("Embedding模型加载成功")
            # 从Embedding模型读取真实向量维度。
            #
            # Qdrant创建集合时必须提前知道每条向量
            # 包含多少个浮点数，因此不能省略这个步骤。
            vector_size = (
                self.embedding_model
                .get_embedding_dimension()
            )

            if vector_size is None:
                raise ValueError(
                    "无法获取Embedding模型的向量维度"
                )

            # 创建整个后端共用的Qdrant存储对象。
            #
            # 如果集合不存在，QdrantMemoryStore会自动创建；
            # 如果已经迁移过旧记忆，则直接打开原集合。
            self.qdrant_store = QdrantMemoryStore(
                vector_size=vector_size,
            )

            print(
                f"Qdrant长期记忆存储器创建成功，"
                f"当前共有"
                f"{self.qdrant_store.count_memories()}条记忆"
            )
            # 创建Qdrant长期记忆业务管理器。
            #
            # store负责数据库底层操作；
            # manager负责判断ADD、UPDATE、DELETE，
            # 并在操作成功后生成JSON备份。
            self.qdrant_memory_manager = (
                QdrantMemoryManager(
                    store=self.qdrant_store,
                    embedding_model=(
                        self.embedding_model
                    ),
                )
            )

            print(
                "Qdrant长期记忆管理器创建成功"
            )
            
        
            # 创建长期记忆写入提取器。
            self.memory_extractor = MemoryExtractor(
                client=self.client,
                model=self.model,
            )

            print("长期记忆提取器创建成功")

            # 创建长期记忆查询规划器。
            self.memory_query_planner = MemoryQueryPlanner(
                client=self.client,
                model=self.model,
            )

            print("长期记忆查询规划器创建成功")

            # 创建玩家态度分析器。
            self.affinity_analyzer = AffinityAnalyzer(
                client=self.client,
                model=self.model,
            )

            print("玩家态度分析器创建成功")

            # 创建好感度管理器。
            self.relationship_manager = RelationshipManager(
                analyzer=self.affinity_analyzer,
            )

            print("好感度管理器创建成功")

            # 创建并初始化全部NPC。
            self.npc_manager = NPCAgentManager(
                client=self.client,
                model=self.model,
            )

            self.npc_manager.initialize_npcs()

            print(
                f"NPC管理器初始化成功，"
                f"当前共有"
                f"{self.npc_manager.get_npc_count()}个NPC。"
            )

            # 创建NPC运行状态管理器。
            self.state_manager = StateManager()

            self.state_manager.initialize_npcs(
                npcs=self.npc_manager.get_all_npcs(),
            )

            print(
                f"NPC状态管理器初始化成功，"
                f"当前共有"
                f"{self.state_manager.get_npc_count()}个状态。"
            )

            # 创建NPC批量背景对话生成器。
            self.batch_dialogue_generator = (
                BatchDialogueGenerator(
                    client=self.client,
                    model=self.model,
                )
            )

            print("批量背景对话生成器创建成功")

            # 创建背景对话缓存管理器。
            self.background_cache = (
                BackgroundDialogueCache(
                    ttl_seconds=(
                        BACKGROUND_CACHE_TTL_SECONDS
                    ),
                )
            )

            print("背景对话缓存管理器创建成功")

            # 创建对话与错误日志记录器。
            self.dialogue_logger = DialogueLogger()

            print("NPC对话日志记录器创建成功")

            # 所有组件成功创建后才标记为已初始化。
            self.initialized = True

            print("赛博小镇全部组件初始化完成")

    def shutdown(self) -> None:
        """安全关闭赛博小镇持有的外部资源。"""

        # 使用与初始化相同的锁，
        # 防止初始化和关闭操作同时执行。
        with self.initialization_lock:
            if not self.initialized:
                return

            # 关闭Qdrant本地数据库客户端，
            # 释放data/qdrant目录对应的文件锁。
            qdrant_store = getattr(
                self,
                "qdrant_store",
                None,
            )

            if qdrant_store is not None:
                try:
                    qdrant_store.close()
                    print("Qdrant长期记忆存储器已关闭")

                except Exception as error:
                    # 关闭阶段不继续抛出异常，
                    # 避免影响FastAPI正常退出。
                    print(
                        f"Qdrant存储器关闭失败：{error}"
                    )

            # OpenAI兼容客户端也提供close()方法。
            llm_client = getattr(
                self,
                "client",
                None,
            )

            if llm_client is not None:
                try:
                    llm_client.close()
                    print("LLM客户端已关闭")

                except Exception as error:
                    print(
                        f"LLM客户端关闭失败：{error}"
                    )

            # 允许同一Python进程以后重新初始化。
            self.initialized = False

            print("赛博小镇全部组件已经释放")


# 创建全局应用容器。
#
# 此处只创建空容器，不会立即加载Embedding模型，
# 真正初始化要调用application_context.initialize()。
application_context = ApplicationContext()