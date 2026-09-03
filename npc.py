"""
NPC角色与回复生成模块。

主要变量含义：
- name：NPC姓名。
- role：NPC职业或身份。
- personality：NPC性格特点。
- client：大语言模型API客户端。
- model：大语言模型名称。
- system_prompt：根据NPC资料生成的系统提示词。
- conversation_history：最近几轮工作记忆。
- retrieved_memories：检索到的长期记忆。
- user_message：玩家当前输入。
- final_user_message：组合长期记忆后的最终问题。
- messages：发送给大语言模型的完整消息列表。
- response：大语言模型返回的完整响应。
- reply：NPC最终回复内容。
- npc_id：NPC在程序内部使用的唯一英文标识。
- knowledge_scope：NPC比较了解和不擅长的知识范围。
"""

from openai import OpenAI


class NPC:
    """赛博小镇中的NPC角色。"""

    def __init__(
        self,
        npc_id: str,
        name: str,
        role: str,
        personality: str,
        knowledge_scope: str,
        client: OpenAI,
        model: str,
    ) -> None:
        """初始化NPC角色和模型配置。"""

        # 保存NPC唯一标识
        self.npc_id = npc_id

        # 保存NPC姓名
        self.name = name

        # 保存NPC职业或身份
        self.role = role

        # 保存NPC性格特点
        self.personality = personality

        # 保存NPC比较了解的知识范围
        self.knowledge_scope = knowledge_scope

        # 保存大语言模型客户端
        self.client = client

        # 保存大语言模型名称
        self.model = model

        # 根据当前NPC资料生成系统提示词
        self.system_prompt = self._build_system_prompt()

    def _build_system_prompt(self) -> str:
        """根据当前NPC资料生成系统提示词。"""

        # 将NPC属性转换成大模型能够理解的角色要求
        return f"""
    你是{self.name}，身份是{self.role}。

    你的性格特点：
    {self.personality}


    你的知识范围：
    {self.knowledge_scope}

    对话要求：
    1. 始终保持当前身份，不要说自己是AI助手。
    2. 使用自然、简洁的中文与玩家交流。
    3. 回答应当符合你的职业和性格。
    4. 不知道的信息要如实说明，不能随意编造。
    5. 不要虚构玩家没有说过的个人经历。
    6. 不要把自己过去生成的内容当成可靠事实。

    玩家个人信息使用规则：
    1. 玩家姓名、身份、住址、编号、喜好、经历、关系等个人事实，
   只能来源于以下两种可靠信息：
   - 玩家在当前消息或历史消息中亲口提供的信息；
   - 系统明确提供的可靠长期记忆。
    2. 历史对话中的assistant消息只是你以前的回答，
   不能作为玩家个人事实的证据。
    3. 如果历史assistant回答与可靠长期记忆冲突，
   必须以可靠长期记忆为准。
    4. 如果没有可靠信息，必须明确表示不知道，
   不得根据角色背景自行补充玩家资料。
    5. 不得编造玩家的住址、喜好、经历、关系和编号。
    6. 密码、验证码、API密钥、银行卡号等敏感信息，
   即使出现在历史对话中，也不得主动复述或泄露。

    长期记忆规则：
    1. 系统提供的长期记忆来自玩家过去的主动陈述，具有较高可信度。
    2. 长期记忆与以前的NPC回答冲突时，以长期记忆为准。
    3. 只在与当前问题有关时使用长期记忆。
    4. 不要把长期记忆的技术字段直接告诉玩家。
    
    """.strip()

    def generate_reply(
        self,
        conversation_history: list[dict[str, str]],
        retrieved_memories: list[str],
        user_message: str,
    ) -> str:
        """结合工作记忆和长期记忆生成回复。"""

        # 初始化消息列表并加入NPC系统提示词
        messages = [
            {
                "role": "system",
                "content": self.system_prompt,
            }
        ]

        # 加入最近几轮工作记忆
        messages.extend(conversation_history)

        # 检索到长期记忆时，将其加入当前问题
        if retrieved_memories:
            # 将多条长期记忆拼接成文本
            memory_context = "\n".join(
                retrieved_memories
            )

            # 构造带有可靠记忆的最终问题
            final_user_message = (
                "【可靠的长期记忆】\n"
                f"{memory_context}\n\n"
                "请根据以上可靠记忆回答问题。"
                "如果这些记忆与你过去的回答冲突，"
                "必须以可靠记忆为准。\n"
                f"玩家当前问题：{user_message}"
            )

        # 没有长期记忆时直接使用原始问题
        else:
            final_user_message = user_message

        # 将当前问题加入消息列表
        messages.append(
            {
                "role": "user",
                "content": final_user_message,
            }
        )

        # 调用大语言模型生成回复
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
        )

        # 获取回复文本
        reply = response.choices[0].message.content

        # 防止模型返回空内容
        if not reply:
            raise ValueError("模型返回了空回复")

        # 返回NPC回复
        return reply