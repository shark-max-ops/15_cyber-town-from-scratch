"""
结构化长期记忆数据模型。

提取器只看到玩家当前说的话，可能不知道数据库中有没有旧记录，所以它先输出：
REMEMBER：这条内容应该记住
FORGET：玩家要求忘记
NONE：不值得记忆

之后由记忆存储模块查询memory_key：
REMEMBER + 不存在相同key
→ ADD
REMEMBER + 已存在相同key
→ UPDATE
FORGET + 存在相同key
→ DELETE
"""

"""

主要类型含义：
- MemoryCandidate：DeepSeek从玩家消息中提取的候选记忆。
- MemoryExtractionResult：一次消息中提取出的全部候选记忆。
- StoredMemory：经过验证并正式保存的长期记忆。

主要变量含义：
- action：记忆意图，包括REMEMBER、FORGET和NONE。
- memory_id：正式记忆的唯一编号。
- memory_type：由模型判断的开放式记忆类型。
- memory_key：用于识别同一属性的稳定键。
- value：记忆中真正有意义的值。
- summary：用于Embedding检索的标准化事实描述。
- importance：记忆重要程度，范围为0～1。
- confidence：模型对提取结果的置信度，范围为0～1。
- sensitive：内容是否包含密码、令牌等敏感信息。
- source：记忆的信息来源。
- source_text：玩家最初输入的原始消息。
- created_at：记忆第一次创建的时间。
- updated_at：记忆最后一次更新的时间。
- embedding：标准化记忆对应的语义向量。
- memories：一条玩家消息中提取出的多条候选记忆。
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class MemoryCandidate(BaseModel):
    """DeepSeek从玩家消息中提取的候选记忆。"""

    # REMEMBER表示希望保存或更新这条信息
    # FORGET表示玩家要求删除相关信息
    # NONE表示没有值得保存的内容
    action: Literal[
        "REMEMBER",
        "FORGET",
        "NONE",
    ] = "NONE"

    # 开放式记忆类型，不限制为固定枚举
    # 示例：profile、preference、plan、experience
    memory_type: str = "other"

    # 描述事实属性的稳定键
    # 示例：player.name、player.favorite_food
    memory_key: str = ""

    # 事实的具体值
    # 示例：陈文浩、葡挞、下个月去上海
    value: str = ""

    # 用于检索的完整标准化描述
    # 示例：玩家的名字是陈文浩
    summary: str = ""

    # 记忆的重要程度
    importance: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
    )

    # 模型对提取结果的把握程度
    confidence: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
    )

    # 是否包含不应该长期保存的敏感信息
    sensitive: bool = False

    # 保存玩家的原始消息，方便检查和追溯
    source_text: str = ""


class MemoryExtractionResult(BaseModel):
    """一条玩家消息对应的记忆提取结果。"""

    # 一条消息可能同时包含多个事实
    memories: list[MemoryCandidate] = Field(
        default_factory=list
    )


class StoredMemory(BaseModel):
    """经过验证并正式保存的长期记忆。"""

    # 每条正式记忆的唯一编号
    memory_id: str

    # 记忆类型由模型根据语义生成
    memory_type: str

    # 用于冲突判断和更新的稳定键
    memory_key: str

    # 事实的具体值
    value: str

    # 用于展示和Embedding检索的事实描述
    summary: str

    # 记忆的重要程度
    importance: float = Field(
        ge=0.0,
        le=1.0,
    )

    # 提取这条记忆时的置信度
    confidence: float = Field(
        ge=0.0,
        le=1.0,
    )

    # 标记这条记忆的信息来源
    source: str = "player_statement"

    # 保留玩家原始消息
    source_text: str

    # 记忆创建时间
    created_at: datetime

    # 记忆最后更新时间
    updated_at: datetime

    # 用于语义检索的Embedding向量
    embedding: list[float] = Field(
        default_factory=list
    )


class MemoryQueryPlan(BaseModel):
    """
    长期记忆查询计划。

    needs_memory：
    当前问题是否需要查询玩家长期记忆。

    memory_keys：
    当前问题可能对应的结构化记忆键。

    semantic_query：
    用于向量检索的标准化查询文本。

    confidence：
    模型对查询规划结果的置信度。

    reason：
    生成该查询计划的简短原因，主要用于调试。
    """

    # 是否需要检索长期记忆。
    needs_memory: bool = False

    # 需要精确匹配的结构化记忆键。
    memory_keys: list[str] = Field(default_factory=list)

    # 经过改写的语义检索文本。
    semantic_query: str = ""

    # 查询规划置信度。
    confidence: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
    )

    # 查询规划原因。
    reason: str = ""