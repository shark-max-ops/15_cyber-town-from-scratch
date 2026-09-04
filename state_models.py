"""
NPC运行状态数据模型模块。

功能说明：
定义NPC在赛博小镇运行期间的动态状态，
包括位置、动作、情绪、背景台词、忙碌状态和当前交互玩家。

这些状态主要服务于后续FastAPI和Godot，
不属于NPC长期记忆。

主要变量含义：
- x：NPC在游戏地图中的横坐标。
- y：NPC在游戏地图中的纵坐标。
- npc_id：NPC唯一编号。
- name：NPC姓名。
- role：NPC身份或职业。
- position：NPC当前地图位置。
- is_busy：NPC当前是否正在处理玩家对话。
- activity_status：NPC当前活动状态。
- current_action：NPC当前动作。
- emotion：NPC当前情绪。
- background_speech：NPC当前背景台词。
- active_player_id：当前正在与NPC交互的玩家ID。
- last_interaction_at：NPC最近一次开始交互的时间。
- updated_at：NPC状态最近更新时间。
- background_action：批量生成的NPC背景动作。
"""

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


# NPC活动状态类型。
NPCActivityStatus = Literal[
    "idle",
    "background",       #NPC正在执行批量生成的背景行为
    "talking",
]


class Position(BaseModel):
    """NPC在游戏地图中的二维坐标。"""

    # 地图横坐标。
    x: float = 0.0

    # 地图纵坐标。
    y: float = 0.0


class NPCState(BaseModel):
    """单个NPC当前的完整运行状态。"""

    # NPC唯一编号。
    npc_id: str

    # NPC姓名。
    name: str

    # NPC身份或职业。
    role: str

    # NPC当前地图位置。
    position: Position = Field(
        default_factory=Position,
    )

    # NPC当前是否正在处理玩家对话。
    is_busy: bool = False

    # NPC当前活动状态。
    activity_status: NPCActivityStatus = "idle"

    # 批量背景系统生成的NPC动作。
    #
    # NPC与玩家聊天时，current_action会临时变成“正在交谈”；
    # 对话结束后，可以恢复这里保存的背景动作。
    background_action: str = "进行日常活动"
    
    # NPC当前正在进行的动作。
    current_action: str = "等待中"

    # NPC当前情绪。
    emotion: str = "平静"

    # NPC当前显示的背景台词。
    background_speech: str = ""

    # 当前正在与NPC对话的玩家。
    #
    # 没有玩家交互时为None。
    active_player_id: str | None = None

    # 最近一次开始玩家交互的时间。
    last_interaction_at: datetime | None = None

    # 状态最近更新时间。
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(
            timezone.utc
        )
    )