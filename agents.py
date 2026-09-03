"""
NPC智能体管理模块。

主要变量含义：
- client：大语言模型API客户端。
- model：大语言模型名称。
- npcs：以npc_id为键、NPC对象为值的字典。
- profile：一名NPC的角色配置。
- npc：根据角色配置创建的NPC对象。
- npc_id：NPC唯一英文标识。
"""

from openai import OpenAI

# 导入NPC类
from npc import NPC

# 导入全部NPC角色配置
from npc_profiles import NPC_PROFILES


class NPCAgentManager:
    """统一创建、保存和查询所有NPC。"""

    def __init__(
        self,
        client: OpenAI,
        model: str,
    ) -> None:
        """初始化NPC管理器。"""

        # 保存大语言模型客户端
        self.client = client

        # 保存大语言模型名称
        self.model = model

        # 保存全部NPC对象
        self.npcs: dict[str, NPC] = {}

    def initialize_npcs(self) -> None:
        """根据角色配置创建全部NPC。"""

        # 先清空旧的NPC对象
        self.npcs.clear()

        # 遍历全部NPC配置
        for profile in NPC_PROFILES:
            # 根据当前配置创建NPC
            npc = NPC(
                npc_id=profile["npc_id"],
                name=profile["name"],
                role=profile["role"],
                personality=profile["personality"],
                knowledge_scope=profile[
                    "knowledge_scope"
                ],
                client=self.client,
                model=self.model,
            )

            # 使用npc_id注册NPC
            self.npcs[npc.npc_id] = npc

    def has_npc(self, npc_id: str) -> bool:
        """判断指定NPC是否存在。"""

        # 检查npc_id是否已经注册
        return npc_id in self.npcs

    def get_npc(
        self,
        npc_id: str,
    ) -> NPC | None:
        """根据npc_id获取NPC对象。"""

        # NPC不存在时返回None
        return self.npcs.get(npc_id)

    def get_all_npcs(self) -> list[NPC]:
        """获取全部NPC对象。"""

        # 将NPC字典的值转换为列表
        return list(self.npcs.values())

    def get_npc_count(self) -> int:
        """获取已经注册的NPC数量。"""

        # 返回NPC字典长度
        return len(self.npcs)