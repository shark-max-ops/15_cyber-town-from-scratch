"""
memory_query_planner.py

长期记忆查询规划器，负责：

1. 分析玩家当前输入是否需要长期记忆；
2. 推断可能对应的memory_key；
3. 将口语问题改写成适合向量检索的文本；
4. 返回结构化MemoryQueryPlan。

该模块不读取记忆内容，只负责制定查询计划。
"""
"""
玩家：我叫什么
↓
MemoryQueryPlanner
↓
needs_memory = true
memory_keys = ["player.name"]
semantic_query = "玩家的姓名"
↓
下一步先精确查找player.name
↓
找不到时再进行向量检索
"""

import json
import re

from openai import OpenAI

from memory_models import MemoryQueryPlan


class MemoryQueryPlanner:
    """使用LLM生成长期记忆查询计划。"""

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

        # 查询规划器的系统提示词。
        self.system_prompt = """
你是一个游戏NPC长期记忆查询规划器。

你的任务不是回答玩家，而是判断玩家当前输入是否需要查询长期记忆，
并生成结构化的查询计划。

长期记忆主要保存玩家过去主动提供的稳定事实，例如：
姓名、身份、喜好、厌恶、习惯、关系、经历、目标、承诺和重要事件。

请根据玩家问题的真实含义，自行推断memory_key。
memory_key不是固定枚举，必须使用稳定、简洁的英文点号形式。

例如：
- 玩家姓名可以表示为 player.name
- 玩家喜欢的食物可以表示为 player.favorite_food
- 玩家正在学习的内容可以表示为 player.current_study
- 玩家与某人的关系可以表示为 player.relationship.person_name

这些仅仅是命名示例，不是固定分类列表。

规则：

1. 如果玩家正在询问过去提供的个人信息，needs_memory应为true。
2. 如果只是普通知识问题、寒暄或当前指令，needs_memory应为false。
3. memory_keys可以包含多个可能的键。
4. semantic_query需要把口语问题改写为明确、完整的检索描述。
5. 不要回答玩家问题。
6. 不要捏造玩家信息。
7. 只能输出JSON，不能输出Markdown代码块或其他文字。

输出格式：

{
  "needs_memory": true,
  "memory_keys": ["player.name"],
  "semantic_query": "玩家的姓名",
  "confidence": 0.95,
  "reason": "玩家正在询问自己的姓名"
}
""".strip()

    def plan(
        self,
        user_message: str,
    ) -> MemoryQueryPlan:
        """根据玩家当前消息生成长期记忆查询计划。"""

        # 调用DeepSeek进行查询意图分析。
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": self.system_prompt,
                },
                {
                    "role": "user",
                    "content": (
                        "请分析下面这条玩家消息，并输出查询计划：\n\n"
                        f"{user_message}"
                    ),
                },
            ],
            temperature=0,
        )

        # 读取模型返回的文本。
        result_text = response.choices[0].message.content

        if not result_text:
            raise ValueError("记忆查询规划器返回了空内容")

        # 清理并解析模型返回的JSON。
        result_data = self._parse_json(
            result_text=result_text,
        )

        # 使用Pydantic验证返回结构。
        query_plan = MemoryQueryPlan.model_validate(
            result_data
        )

        # 如果不需要长期记忆，就清理无用查询字段。
        if not query_plan.needs_memory:
            query_plan.memory_keys = []
            query_plan.semantic_query = ""

        # 如果需要记忆但没有生成语义查询，
        # 就使用原始玩家消息作为后备查询。
        if (
            query_plan.needs_memory
            and not query_plan.semantic_query.strip()
        ):
            query_plan.semantic_query = user_message

        return query_plan

    #_parse_json() 只需要处理传入的 result_text,它不需要使用这些对象属性：self.client等
    @staticmethod
    def _parse_json(
        result_text: str,
    ) -> dict:
        """从模型输出中提取并解析JSON对象。"""

        # 去除文本首尾空白。
        cleaned_text = result_text.strip()

        # 去除可能出现的Markdown代码块标记。
        cleaned_text = re.sub(
            r"^```(?:json)?\s*",
            "",
            cleaned_text,
            flags=re.IGNORECASE,
        )

        cleaned_text = re.sub(
            r"\s*```$",
            "",
            cleaned_text,
        )

        try:
            # 优先直接解析完整文本。
            return json.loads(cleaned_text)

        except json.JSONDecodeError:
            # 如果模型额外输出了文字，
            # 尝试截取第一个完整JSON对象。
            json_match = re.search(
                r"\{.*\}",
                cleaned_text,
                flags=re.DOTALL,
            )

            if not json_match:
                raise ValueError(
                    f"查询规划结果不是有效JSON：{result_text}"
                )

            try:
                return json.loads(
                    json_match.group()
                )

            except json.JSONDecodeError as error:
                raise ValueError(
                    f"查询规划JSON解析失败：{result_text}"
                ) from error