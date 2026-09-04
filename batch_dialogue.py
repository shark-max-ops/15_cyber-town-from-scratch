"""
batch_dialogue.py

文件作用：
使用一次DeepSeek API调用，为全部NPC批量生成背景台词、
动作和情绪，并验证模型返回的JSON是否完整、正确。

该模块只使用NPC公开资料，不读取玩家工作记忆或长期记忆，
避免玩家个人信息出现在NPC背景对话中。

主要类：

BatchDialogueGenerator：
批量背景对话生成器，负责构造提示词、调用DeepSeek、
解析JSON并检查NPC是否完整。

主要变量：
client：
OpenAI兼容客户端，用来调用DeepSeek API。
model：
当前使用的DeepSeek模型名称。
system_prompt：
批量背景对话生成规则。
npcs：
当前需要生成背景状态的NPC对象列表。
scene_context：
当前场景描述，例如时间、天气、地点和正在发生的事件。
npc_profiles：
从NPC对象中提取出来的公开角色资料列表。
npc_profiles_text：
转换成JSON字符串后的NPC公开资料。
user_prompt：
本次发送给DeepSeek的场景信息和NPC资料。
response：
DeepSeek API返回的完整响应对象。
result_text：
从API响应中取出的原始文本。
result_data：
将原始JSON文本解析后得到的Python字典。
result：
经过Pydantic验证的批量背景对话结果。
expected_ids：
程序要求生成背景状态的NPC ID集合。
returned_ids：
DeepSeek实际返回的NPC ID集合。
missing_ids：
应该生成但没有返回的NPC ID集合。
unknown_ids：
DeepSeek自行生成的未知NPC ID集合。
"""

import json
import re

from openai import OpenAI

from background_models import (
    BatchBackgroundDialogueResult,
)
from npc import NPC


class BatchDialogueGenerator:
    """通过一次LLM调用生成所有NPC的背景对话。"""

    def __init__(
        self,
        client: OpenAI,
        model: str,
    ) -> None:
        """保存LLM客户端和模型名称。"""

        # OpenAI兼容客户端。
        self.client = client

        # DeepSeek模型名称。
        self.model = model

        # 批量生成器的固定系统提示词。
        self.system_prompt = """
你是一个游戏NPC背景状态生成器。

你的任务是根据场景信息和NPC资料，
一次性为所有NPC生成自然、简短且相互协调的背景台词和行为。

背景状态用于玩家尚未主动交谈时展示，
不是对玩家问题的回复。

生成规则：

1. 必须为输入中的每个NPC生成且只生成一条记录。
2. npc_id必须与输入资料完全一致，不得修改或创造新ID。
3. speech是NPC当前自然说出的简短台词。
4. action是NPC当前正在做的简短动作。
5. emotion是NPC当前的情绪。
6. 内容必须符合NPC身份、性格和知识范围。
7. 不同NPC的状态可以围绕同一场景互相关联。
8. 不得提及玩家姓名、喜好、密码、编号等个人记忆。
9. 不得替玩家做出行为或决定。
10. 不要输出Markdown，只能输出一个JSON对象。

输出格式：

{
  "scene_summary": "当前场景的简短描述",
  "dialogues": [
    {
      "npc_id": "NPC的原始ID",
      "speech": "NPC的背景台词",
      "action": "NPC当前动作",
      "emotion": "NPC当前情绪"
    }
  ]
}
""".strip()

    def generate(
        self,
        npcs: list[NPC],
        scene_context: str,
    ) -> BatchBackgroundDialogueResult:
        """通过一次LLM请求生成全部NPC背景状态。"""

        # NPC列表不能为空。
        if not npcs:
            raise ValueError("批量生成时NPC列表不能为空")

        # 将NPC对象转换成可以放进提示词的数据。
        npc_profiles = []

        for npc in npcs:
            # 每个NPC只提供角色公开资料，
            # 不提供玩家对话历史和长期记忆。
            npc_profiles.append(
                {
                    "npc_id": npc.npc_id,
                    "name": npc.name,
                    "role": npc.role,
                    "personality": npc.personality,
                    "knowledge_scope": npc.knowledge_scope,
                }
            )

        # 将NPC资料转换成格式清晰的JSON文本。
        npc_profiles_text = json.dumps(
            npc_profiles,
            ensure_ascii=False,
            indent=2,
        )

        # 构造本次批量生成的用户提示词。
        user_prompt = f"""
当前场景：

{scene_context}

NPC资料：

{npc_profiles_text}

请为以上所有NPC生成当前背景状态。
必须严格使用NPC资料中的npc_id。
""".strip()

        # 一次API调用生成全部NPC背景状态。
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": self.system_prompt,
                },
                {
                    "role": "user",
                    "content": user_prompt,
                },
            ],
            temperature=0.8,
        )

        # 读取模型返回文本。
        result_text = response.choices[0].message.content

        if not result_text:
            raise ValueError("批量背景对话生成器返回了空内容")

        # 从模型输出中解析JSON。
        result_data = self._parse_json(
            result_text=result_text,
        )

        # 使用Pydantic检查字段和数据类型。
        result = BatchBackgroundDialogueResult.model_validate(
            result_data
        )

        # 检查返回的NPC是否与输入NPC完全对应。
        self._validate_npc_ids(
            npcs=npcs,
            result=result,
        )

        return result

    @staticmethod
    def _parse_json(
        result_text: str,
    ) -> dict:
        """清理并解析模型返回的JSON对象。"""

        # 清理首尾空白。
        cleaned_text = result_text.strip()

        # 去除模型可能添加的Markdown代码块开头。
        cleaned_text = re.sub(
            r"^```(?:json)?\s*",
            "",
            cleaned_text,
            flags=re.IGNORECASE,
        )

        # 去除模型可能添加的Markdown代码块结尾。
        cleaned_text = re.sub(
            r"\s*```$",
            "",
            cleaned_text,
        )

        try:
            # 优先直接解析完整返回文本。
            return json.loads(cleaned_text)

        except json.JSONDecodeError:
            # 模型输出额外说明时，
            # 尝试截取最外层JSON对象。
            json_match = re.search(
                r"\{.*\}",
                cleaned_text,
                flags=re.DOTALL,
            )

            if not json_match:
                raise ValueError(
                    f"没有找到有效JSON：{result_text}"
                )

            try:
                return json.loads(
                    json_match.group()
                )

            except json.JSONDecodeError as error:
                raise ValueError(
                    f"批量背景对话JSON解析失败：{result_text}"
                ) from error

    @staticmethod
    def _validate_npc_ids(
        npcs: list[NPC],
        result: BatchBackgroundDialogueResult,
    ) -> None:
        """检查模型是否为每个NPC生成了唯一记录。"""

        # 取得程序要求生成的NPC ID。
        expected_ids = {
            npc.npc_id
            for npc in npcs
        }

        # 取得模型实际返回的NPC ID列表。
        returned_id_list = [
            dialogue.npc_id
            for dialogue in result.dialogues
        ]

        # 转成集合，方便比较缺失和多余的ID。
        returned_ids = set(returned_id_list)

        # 检查同一个NPC是否被生成了多次。
        if len(returned_id_list) != len(returned_ids):
            raise ValueError(
                "批量生成结果包含重复的npc_id"
            )

        # 找出没有生成背景状态的NPC。
        missing_ids = expected_ids - returned_ids

        if missing_ids:
            raise ValueError(
                f"以下NPC缺少背景状态："
                f"{sorted(missing_ids)}"
            )

        # 找出模型自行创造的未知NPC。
        unknown_ids = returned_ids - expected_ids

        if unknown_ids:
            raise ValueError(
                f"模型返回了未知NPC："
                f"{sorted(unknown_ids)}"
            )