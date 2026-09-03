"""
长期记忆智能提取模块。

主要类型含义：
- MemoryExtractor：使用DeepSeek分析玩家消息的记忆提取器。
- MemoryExtractionResult：一条消息对应的结构化提取结果。

主要变量含义：
- client：DeepSeek API客户端。
- model：用于记忆提取的大语言模型名称。
- user_message：玩家当前输入的原始消息。
- messages：发送给记忆提取模型的消息列表。
- response：DeepSeek返回的完整响应对象。
- raw_result：DeepSeek返回的原始字符串。
- parsed_data：从模型字符串中解析出的Python字典。
- extraction_result：经过Pydantic校验的提取结果。
- candidate：一条候选长期记忆。
- json_text：从模型回复中提取出的JSON字符串。
- start_index：JSON对象左大括号的位置。
- end_index：JSON对象右大括号的位置。
"""

import json

from openai import OpenAI

# 导入结构化记忆数据模型
from memory_models import MemoryExtractionResult


class MemoryExtractor:
    """使用大语言模型提取玩家长期记忆。"""

    def __init__(
        self,
        client: OpenAI,
        model: str,
    ) -> None:
        """初始化记忆提取器。"""

        # 保存DeepSeek客户端
        self.client = client

        # 保存记忆提取使用的模型名称
        self.model = model

        # 构建专门用于提取记忆的系统提示词
        self.system_prompt = self._build_system_prompt()

    def _build_system_prompt(self) -> str:
        """构建长期记忆提取提示词。"""

        # 返回严格的记忆提取规则
        return """
你是赛博小镇的长期记忆提取器。

你的任务不是与玩家对话，而是分析玩家最新发送的一条消息，
判断其中是否包含值得长期保存的信息，并输出严格的JSON。

【需要保存的信息】

包括但不限于：
1. 玩家身份，例如姓名、职业、专业、学校；
2. 长期偏好，例如喜欢的食物、运动、颜色、兴趣；
3. 稳定习惯，例如经常做的事情、作息习惯；
4. 重要经历，例如参加过的项目、比赛、旅行；
5. 明确计划，例如准备考试、计划旅行、准备完成某个项目；
6. 人际关系，例如朋友、老师、家人；
7. 玩家主动要求NPC记住的非敏感信息；
8. 对旧信息的修改、否定或遗忘要求。

【不需要保存的信息】

1. 普通知识问题；
2. 临时寒暄；
3. 没有说完整的句子；
4. NPC自己生成或推测的信息；
5. 无法从当前玩家原话中确定的信息；
6. 一次性的普通命令；
7. 没有长期价值的临时内容。

【敏感信息】

如果消息包含以下内容，sensitive必须为true：
1. 密码；
2. API密钥；
3. 验证码；
4. 银行卡号；
5. 身份证号；
6. 访问令牌；
7. 私钥或其他认证凭据。

敏感信息仍然可以被识别出来，
但后续程序不会将它正式保存。

【action规则】

- REMEMBER：玩家提供了需要保存或更新的信息；
- FORGET：玩家明确要求删除、忘记某条信息；
- NONE：没有值得保存的信息。

如果玩家只是修改某项信息，例如：
“我现在最喜欢蛋糕，不喜欢葡挞了”，
只需要为最新事实生成REMEMBER，
memory_key继续使用同一个稳定键。

如果玩家只说：
“我已经不喜欢葡挞了”，
则生成FORGET。

【memory_type规则】

memory_type是开放式类型，不限于固定选项。

可以参考：
- profile
- preference
- habit
- plan
- experience
- relationship
- project
- education
- other

【memory_key规则】

memory_key必须使用稳定、简短的英文层级名称。

示例：
- player.name
- player.education.major
- player.preference.favorite_food
- player.preference.favorite_sport
- player.plan.travel
- player.project.current
- player.relationship.teacher

描述相同属性的消息必须尽量使用相同memory_key。

【内容拆分规则】

如果一句话包含多个独立事实，必须拆成多条记忆。

例如：
“我叫陈文浩，我喜欢葡挞。”

应该拆成：
1. player.name = 陈文浩
2. player.preference.favorite_food = 葡挞

【评分规则】

importance范围为0到1：
- 核心身份信息：0.8～1.0
- 稳定偏好和重要经历：0.6～0.8
- 普通计划和一般信息：0.4～0.7
- 临时或价值较低的信息：低于0.4

confidence范围为0到1：
- 玩家明确陈述：0.9～1.0
- 表达略有歧义：0.6～0.8
- 无法确定：不要生成记忆

【输出格式】

只能返回下面格式的JSON对象，不要输出解释，不要使用Markdown代码块：

{
  "memories": [
    {
      "action": "REMEMBER",
      "memory_type": "preference",
      "memory_key": "player.preference.favorite_food",
      "value": "葡挞",
      "summary": "玩家喜欢吃葡挞",
      "importance": 0.7,
      "confidence": 0.95,
      "sensitive": false,
      "source_text": ""
    }
  ]
}

如果没有值得保存的内容，返回：

{
  "memories": []
}
""".strip()

    def extract(
        self,
        user_message: str,
    ) -> MemoryExtractionResult:
        """从一条玩家消息中提取长期记忆。"""

        # 清理玩家输入
        cleaned_message = user_message.strip()

        # 空消息直接返回空结果
        if not cleaned_message:
            return MemoryExtractionResult()

        # 为记忆提取单独构造消息
        # 不传入NPC回复，防止NPC编造内容污染记忆
        messages = [
            {
                "role": "system",
                "content": self.system_prompt,
            },
            {
                "role": "user",
                "content": cleaned_message,
            },
        ]

        # 单独调用DeepSeek进行记忆提取
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0.0,
        )

        # 获取模型返回的原始内容
        raw_result = response.choices[0].message.content

        # 防止模型返回空内容
        if not raw_result:
            raise ValueError("记忆提取模型返回了空内容")

        # 从模型输出中解析JSON
        parsed_data = self._parse_json(raw_result)

        # 使用Pydantic检查字段和数据类型
        extraction_result = (
            MemoryExtractionResult.model_validate(
                parsed_data
            )
        )

        # 清理无效的NONE记忆
        valid_memories = []

        # 遍历全部候选记忆
        for candidate in extraction_result.memories:
            # NONE不需要交给后续存储模块
            if candidate.action == "NONE":
                continue

            # source_text始终使用真实玩家原话
            # 不信任模型自己生成的source_text
            candidate.source_text = cleaned_message

            # 保存有效候选记忆
            valid_memories.append(candidate)

        # 返回经过清理的结构化结果
        return MemoryExtractionResult(
            memories=valid_memories
        )

    def _parse_json(
        self,
        raw_result: str,
    ) -> dict:
        """从模型回复中安全提取JSON对象。"""

        # 清理模型回复两侧空格
        json_text = raw_result.strip()

        # 查找第一个左大括号
        start_index = json_text.find("{")

        # 查找最后一个右大括号
        end_index = json_text.rfind("}")

        # 没有找到完整JSON对象时抛出异常
        if (
            start_index == -1
            or end_index == -1
            or end_index < start_index
        ):
            raise ValueError(
                "记忆提取模型没有返回有效JSON"
            )

        # 截取JSON对象
        json_text = json_text[
            start_index:end_index + 1
        ]

        try:
            # 将JSON字符串转换成Python字典
            parsed_data = json.loads(json_text)

        # JSON格式不正确时转换为更清晰的错误
        except json.JSONDecodeError as error:
            raise ValueError(
                "记忆提取模型返回的JSON格式错误"
            ) from error

        # 最外层必须是JSON对象
        if not isinstance(parsed_data, dict):
            raise ValueError(
                "记忆提取结果必须是JSON对象"
            )

        # 返回解析完成的数据
        return parsed_data