"""
NPC好感度数据模型模块。

功能说明：
定义玩家态度分析结果和NPC好感度记录的数据结构，
使用Pydantic验证分数、等级、置信度和时间等字段。

主要变量含义：
- attitude：DeepSeek判断出的玩家态度。
- score_change：本轮对话引起的好感度变化值。
- reason：好感度发生变化的原因。
- confidence：态度分析结果的可信度。
- npc_id：NPC唯一编号。
- player_id：玩家唯一编号。
- score：当前好感度分数，范围为0到100。
- level：当前好感度等级。
- interaction_count：玩家与NPC成功对话的总次数。
- last_change：最近一次好感度变化值。
- last_reason：最近一次好感度变化原因。
- created_at：好感度记录首次创建时间。
- updated_at：好感度记录最近更新时间。
- recent_message_hashes：近期玩家消息的哈希列表，用于限制重复刷分。
- relationship：更新后的NPC好感度记录。
- analysis：DeepSeek给出的原始态度分析结果。
- applied_change：经过程序规则修正后实际应用的分数变化。
- duplicate_message：玩家消息是否与近期消息重复。
"""

# datetime用于记录好感度创建和更新时间。
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


# 好感度等级类型。
AffinityLevel = Literal[
    "陌生",
    "熟悉",
    "友好",
    "亲密",
    "挚友",
]

# 玩家态度类型。
PlayerAttitude = Literal[
    "friendly",
    "neutral",
    "unfriendly",
]


class AffinityAnalysisResult(BaseModel):
    """DeepSeek对本轮玩家态度的分析结果。"""

    # 玩家本轮表现出的态度。
    attitude: PlayerAttitude = "neutral"

    # 本轮好感度变化值。
    #
    # 当前允许范围：
    # 不友好最低-3分，友好最高+5分。
    score_change: int = Field(
        default=2,
        ge=-3,
        le=5,
    )

    # 好感度变化的简短原因。
    reason: str = "普通交流"

    # 模型对分析结果的置信度。
    confidence: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
    )


class RelationshipRecord(BaseModel):
    """一个玩家与一个NPC之间的好感度记录。"""

    # NPC唯一编号，例如lin_zhou。
    npc_id: str

    # 玩家唯一编号。
    #
    # 当前终端版本只有一个玩家，
    # 后面先统一使用default_player。
    player_id: str = "default_player"

    # 当前好感度分数。
    score: int = Field(
        default=0,
        ge=0,
        le=100,
    )

    # 当前好感度等级。
    level: AffinityLevel = "陌生"

    # 玩家与该NPC的累计有效对话次数。
    interaction_count: int = Field(
        default=0,
        ge=0,
    )
    # 最近一次实际应用的好感度变化值。
    last_change: int = Field(
        default=0,
        ge=-3,
        le=5,
    )

    # 最近一次好感度变化原因。
    last_reason: str = "尚未发生互动"

    # 好感度记录首次创建时间。
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(
            timezone.utc
        )
    )

    # 好感度记录最近更新时间。
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(
            timezone.utc
        )
    )

    # 最近玩家消息的哈希值。
    #
    # 只保存哈希，不保存额外的玩家原文，
    # 用于判断玩家是否重复发送相同内容刷好感度。
    recent_message_hashes: list[str] = Field(
        default_factory=list,
    )

    # 最近一次好感度变化值。
    last_change: int = Field(
        default=0,
        ge=-3,
        le=5,
    )

    # 最近一次变化的原因。
    last_reason: str = ""

    # 记录首次创建时间。
    created_at: datetime

    # 记录最近更新时间。
    updated_at: datetime



class RelationshipUpdateResult(BaseModel):
    """一次好感度更新的完整结果。"""

    # 更新后的好感度记录。
    relationship: RelationshipRecord

    # DeepSeek返回的原始态度分析结果。
    analysis: AffinityAnalysisResult

    # 经过防刷分和置信度校正后，
    # 实际应用到好感度上的变化值。
    applied_change: int = Field(
        ge=-3,
        le=5,
    )

    # 当前消息是否与近期消息重复。
    duplicate_message: bool = False