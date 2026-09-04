"""
background_models.py

文件作用：
定义批量背景对话使用的Pydantic数据模型，
统一约束DeepSeek返回的数据格式。

主要类：

NPCBackgroundDialogue：
保存单个NPC当前的背景台词、动作和情绪。
BatchBackgroundDialogueResult：
保存一次批量生成的完整场景结果。

主要变量：
npc_id：
NPC唯一编号，例如lin_zhou，用来确定背景状态属于哪个NPC。
speech：
NPC当前自然说出的背景台词。
action：
NPC当前正在进行的动作。
emotion：
NPC当前表现出来的情绪。
scene_summary：
当前小镇场景的整体简短描述。
dialogues：
全部NPC背景状态组成的列表。
generated_at：
本批背景对话生成的时间，用于判断缓存是否过期。
scene_context：
生成本批背景对话时使用的场景信息。
result：
经过验证的完整批量背景对话结果。
"""

from pydantic import BaseModel, Field
# datetime用于记录背景对话的生成时间。
from datetime import datetime

class NPCBackgroundDialogue(BaseModel):
    """单个NPC的背景对话和行为状态。"""

    # NPC唯一编号，例如lin_zhou。
    npc_id: str

    # NPC自然说出的背景台词。
    speech: str

    # NPC当前正在进行的动作。
    action: str

    # NPC当前表现出来的情绪。
    emotion: str


class BatchBackgroundDialogueResult(BaseModel):
    """一次批量生成的全部NPC背景状态。"""

    # 当前场景的简短整体描述。
    scene_summary: str = ""

    # 所有NPC的背景台词和行为。
    dialogues: list[NPCBackgroundDialogue] = Field(
        default_factory=list,
    )

class BackgroundDialogueCacheRecord(BaseModel):
    """保存在本地缓存文件中的完整背景对话记录。"""

    # 背景对话生成时间。
    generated_at: datetime

    # 生成背景对话时使用的场景描述。
    scene_context: str

    # DeepSeek批量生成的背景对话结果。
    result: BatchBackgroundDialogueResult