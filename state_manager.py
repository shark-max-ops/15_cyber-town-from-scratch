"""
NPC运行状态管理模块。

功能说明：
负责初始化和管理全部NPC的动态状态，
同步批量生成的背景动作，控制NPC对话占用与释放，
并为后续FastAPI并发请求提供安全的状态访问接口。

主要变量含义：
- npc_states：以npc_id为键保存的全部NPC状态。
- state_lock：保护NPC状态的线程锁，避免并发修改冲突。
- npcs：需要初始化状态的NPC对象列表。
- npc_id：NPC唯一编号。
- player_id：当前请求与NPC交互的玩家ID。
- npc_state：指定NPC当前的运行状态。
- background_result：批量生成的全部NPC背景状态。
- background_map：npc_id到背景对话的映射。
- position：NPC在Godot地图中的二维坐标。
- is_busy：NPC当前是否已被其他玩家占用。
- current_action：NPC当前实际显示的动作。
- background_action：NPC没有与玩家交谈时的背景动作。
- active_player_id：当前占用NPC的玩家ID。
- last_interaction_at：NPC最近一次开始交互的时间。
"""

from datetime import datetime, timezone
from threading import RLock   #可重入锁（Reentrant Lock），允许同一线程多次获取，确保复杂操作中的状态一致性。

from background_models import (
    BatchBackgroundDialogueResult,
)
from npc import NPC
from state_models import NPCState, Position


# 第一个NPC的默认横坐标。
DEFAULT_START_X = 300.0

# 相邻NPC之间的默认横向距离。
DEFAULT_POSITION_SPACING = 200.0

# 所有NPC的默认纵坐标。
DEFAULT_START_Y = 200.0


class StateManager:
    """全部NPC动态运行状态的统一管理器。"""

    def __init__(self) -> None:
        """创建空状态表和可重入线程锁。"""

        # 保存全部NPC的当前状态。
        self.npc_states: dict[str, NPCState] = {}

        # RLock用于保护状态的读取与修改。
        #
        # 后续FastAPI同时收到多个请求时，
        # 可以避免两个玩家同时占用同一个NPC。
        self.state_lock = RLock()

    def initialize_npcs(
        self,
        npcs: list[NPC],
    ) -> None:
        """根据NPC对象列表初始化运行状态。"""

        # 所有初始化操作都在同一把锁内完成。
        with self.state_lock:
            # 重新初始化时先清空旧运行状态。
            self.npc_states.clear()

            # 为每个NPC自动分配一个默认地图位置。
            for index, npc in enumerate(npcs):
                position = Position(
                    x=(
                        DEFAULT_START_X
                        + index
                        * DEFAULT_POSITION_SPACING
                    ),
                    y=DEFAULT_START_Y,
                )

                # 创建NPC初始状态。
                self.npc_states[npc.npc_id] = NPCState(
                    npc_id=npc.npc_id,
                    name=npc.name,
                    role=npc.role,
                    position=position,
                )

    def has_npc(
        self,
        npc_id: str,
    ) -> bool:
        """判断指定NPC状态是否存在。"""

        # 使用锁保护字典读取。
        with self.state_lock:
            return npc_id in self.npc_states

    def get_npc_state(
        self,
        npc_id: str,
    ) -> NPCState | None:
        """获取指定NPC的状态副本。"""

        # 使用锁保护状态读取。
        with self.state_lock:
            npc_state = self.npc_states.get(
                npc_id
            )

            if npc_state is None:
                return None

            # 返回深拷贝，外部代码获得副本后修改不会影响内部状态；
            # model_copy(deep=True) 是 Pydantic 模型提供的深拷贝方法。
            return npc_state.model_copy(
                deep=True,
            )

    def get_all_npc_states(
        self,
    ) -> list[NPCState]:
        """获取全部NPC的状态副本。"""

        # 使用锁保护状态读取。
        with self.state_lock:
            return [
                npc_state.model_copy(deep=True)
                for npc_state
                in self.npc_states.values()
            ]

    def get_npc_count(self) -> int:
        """返回当前NPC状态数量。"""

        # 使用锁保护字典读取。
        with self.state_lock:
            return len(self.npc_states)

    def is_npc_busy(
        self,
        npc_id: str,
    ) -> bool:
        """检查指定NPC当前是否正在与玩家对话。"""

        # 使用锁保护状态读取。
        with self.state_lock:
            npc_state = self.npc_states.get(
                npc_id
            )

            # NPC不存在时返回False。
            if npc_state is None:
                return False

            return npc_state.is_busy

    def try_begin_interaction(
        self,
        npc_id: str,
        player_id: str,
    ) -> bool:
        """尝试让玩家占用NPC并开始交互。"""

        # “检查是否忙碌”和“设置忙碌”
        # 必须在同一次加锁操作中完成。
        with self.state_lock:
            npc_state = self.npc_states.get(
                npc_id
            )

            # NPC不存在时无法开始交互。
            if npc_state is None:
                return False

            # NPC已经被占用时拒绝新的交互。
            if npc_state.is_busy:
                return False

            # 将NPC设置为对话状态。
            npc_state.is_busy = True
            npc_state.activity_status = "talking"
            npc_state.current_action = (
                "正在与玩家交谈"
            )
            npc_state.active_player_id = player_id
            npc_state.last_interaction_at = (
                datetime.now(timezone.utc)
            )
            npc_state.updated_at = (
                datetime.now(timezone.utc)
            )

            return True

    def end_interaction(
        self,
        npc_id: str,
        player_id: str,
    ) -> bool:
        """结束玩家与指定NPC之间的交互。"""

        # 使用锁保护状态修改。
        with self.state_lock:
            npc_state = self.npc_states.get(
                npc_id
            )

            # NPC不存在时无法释放。
            if npc_state is None:
                return False

            # NPC当前没有被占用时无需释放。
            if not npc_state.is_busy:
                return False

            # 只有实际占用NPC的玩家才能释放它。
            if npc_state.active_player_id != player_id:
                return False

            # 清除对话占用信息。
            npc_state.is_busy = False
            npc_state.active_player_id = None

            # 恢复NPC被玩家打断前的背景动作。
            npc_state.current_action = (
                npc_state.background_action
            )

            # 存在背景状态时恢复为background，
            # 否则恢复为idle。
            if npc_state.background_speech:
                npc_state.activity_status = (
                    "background"
                )
            else:
                npc_state.activity_status = "idle"

            npc_state.updated_at = (
                datetime.now(timezone.utc)
            )

            return True

    def update_background_states(
        self,
        background_result: (
            BatchBackgroundDialogueResult
        ),
    ) -> None:
        """将批量生成结果同步到NPC运行状态。"""

        # 建立npc_id到背景状态的映射。
        background_map = {
            dialogue.npc_id: dialogue
            for dialogue
            in background_result.dialogues
        }

        # 使用锁保护批量状态更新。
        with self.state_lock:
            for npc_id, npc_state in (
                self.npc_states.items()
            ):
                # 查找当前NPC的新背景状态。
                background_dialogue = (
                    background_map.get(npc_id)
                )

                # 批量结果中没有该NPC时跳过。
                if background_dialogue is None:
                    continue

                # 保存批量生成的背景动作。
                npc_state.background_action = (
                    background_dialogue.action
                )

                # 更新背景情绪和台词。
                npc_state.emotion = (
                    background_dialogue.emotion
                )
                npc_state.background_speech = (
                    background_dialogue.speech
                )

                # NPC没有与玩家交谈时，
                # 将当前动作更新成背景动作。
                if not npc_state.is_busy:
                    npc_state.activity_status = (
                        "background"
                    )
                    npc_state.current_action = (
                        background_dialogue.action
                    )

                # 更新状态修改时间。
                npc_state.updated_at = (
                    datetime.now(timezone.utc)
                )

    def update_position(
        self,
        npc_id: str,
        position: Position,
    ) -> bool:
        """更新指定NPC在游戏地图中的位置。"""

        # 使用锁保护位置修改。
        with self.state_lock:
            npc_state = self.npc_states.get(
                npc_id
            )

            # NPC不存在时更新失败。
            if npc_state is None:
                return False

            # 保存位置副本，避免外部继续修改。
            npc_state.position = position.model_copy(
                deep=True,
            )
            npc_state.updated_at = (
                datetime.now(timezone.utc)
            )

            return True