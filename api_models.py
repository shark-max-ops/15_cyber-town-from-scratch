"""
FastAPI请求与响应数据模型模块。

功能说明：
规定前端和后端之间传递的 JSON 应该长什么样。
负责：
检查前端请求是否缺少字段或格式错误；
规定后端响应包含哪些字段；
帮助 FastAPI 自动生成接口文档；
防止后端返回结构混乱的数据。，

包括健康检查、NPC对话、NPC状态、好感度和背景对话。

主要变量含义：
- status：后端服务当前运行状态。
- message：后端返回的说明信息。
- version：后端服务版本号。
- npc_count：当前NPC总数。
- npc_id：NPC唯一编号。
- npc_name：NPC姓名。
- player_id：玩家唯一编号。
- player_message：玩家发送给NPC的消息。
- npc_reply：NPC生成的回复。
- affinity_score：玩家与NPC当前的好感度分数。
- affinity_level：玩家与NPC当前的好感度等级。
- affinity_change：本轮对话产生的好感度变化。
- interaction_count：玩家与NPC累计互动次数。
- retrieved_memory_count：本轮检索到的长期记忆数量。
- npcs：全部NPC运行状态列表。
- scene_summary：当前赛博小镇场景概要。
- dialogues：全部NPC背景对话列表。
- generated_at：背景对话生成时间。
"""

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from background_models import NPCBackgroundDialogue
from relationship_models import AffinityLevel
from state_models import NPCState


class HealthResponse(BaseModel):
    """后端健康检查响应。"""

    # 后端服务运行状态。
    status: str = "running"

    # 后端服务说明。
    message: str = "赛博小镇后端正在运行"

    # 当前后端版本号。
    version: str = "1.0.0"

    # 当前初始化完成的NPC数量。
    npc_count: int = Field(
        default=0,
        ge=0,
    )


class DialogueRequest(BaseModel):
    """玩家向NPC发送的对话请求。"""

    # 玩家选择的NPC唯一编号。
    npc_id: str = Field(
        min_length=1,
        max_length=100,
    )

    # 当前玩家唯一编号。
    player_id: str = Field(
        default="default_player",
        min_length=1,
        max_length=100,
    )

    # 玩家本轮发送的消息。
    player_message: str = Field(
        min_length=1,
        max_length=2000,
    )

    #@field_validator：它的作用是将下方的函数注册为指定字段的专属校验器，在数据赋值给模型前自动执行清洗和校验逻辑。
    @field_validator(
        "npc_id",
        "player_id",
        "player_message",
    )
    @classmethod       #@classmethod：它的作用是将下方的函数声明为类级别的方法，让 Pydantic V2 能在实例尚未创建时直接调用该方法进行数据预校验。
    def strip_and_validate_text(
        cls,
        value: str,
    ) -> str:
        """清理文本首尾空格并拒绝纯空白内容。"""

        # 删除文本首尾空格。
        cleaned_value = value.strip()

        # 纯空格内容不能作为有效请求。
        if not cleaned_value:
            raise ValueError("字段内容不能为空")

        return cleaned_value


class DialogueResponse(BaseModel):
    """NPC完成一轮对话后的响应。"""

    # NPC唯一编号。
    npc_id: str

    # NPC姓名。
    npc_name: str

    # NPC生成的回复。
    npc_reply: str

    # 更新后的好感度分数。
    affinity_score: int = Field(
        ge=0,
        le=100,
    )

    # 更新后的好感度等级。
    affinity_level: AffinityLevel

    # 本轮实际应用的好感度变化。
    affinity_change: int = Field(
        ge=-3,
        le=5,
    )

    # 本轮检索到的长期记忆数量。
    retrieved_memory_count: int = Field(
        default=0,
        ge=0,
    )


class NPCStatusListResponse(BaseModel):
    """全部NPC运行状态响应。"""

    # 当前NPC总数。
    npc_count: int = Field(
        default=0,
        ge=0,
    )

    # 全部NPC运行状态。
    npcs: list[NPCState] = Field(
        default_factory=list,
    )


class AffinityResponse(BaseModel):
    """玩家与指定NPC之间的好感度响应。"""

    # NPC唯一编号。
    npc_id: str

    # 玩家唯一编号。
    player_id: str

    # 当前好感度分数。
    affinity_score: int = Field(
        ge=0,
        le=100,
    )

    # 当前好感度等级。
    affinity_level: AffinityLevel

    # 累计有效互动次数。
    interaction_count: int = Field(
        default=0,
        ge=0,
    )

    # 最近一次实际好感度变化。
    last_change: int = Field(
        default=0,
        ge=-3,
        le=5,
    )

    # 最近一次好感度变化原因。
    last_reason: str = ""


class BackgroundDialogueResponse(BaseModel):
    """NPC批量背景对话响应。"""

    # 当前场景的整体描述。
    scene_summary: str

    # 背景对话生成时间。
    generated_at: datetime

    # 全部NPC的背景状态。
    dialogues: list[NPCBackgroundDialogue] = Field(
        default_factory=list,
    )