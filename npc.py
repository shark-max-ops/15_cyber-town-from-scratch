"""
NPC角色与回复生成模块。

功能说明：
定义NPC对象，构建角色系统提示词，
并结合工作记忆、长期记忆和当前好感度生成回复。

主要变量含义：
- npc_id：NPC唯一编号。
- name：NPC姓名。
- role：NPC身份或职业。
- personality：NPC性格特点。
- knowledge_scope：NPC熟悉的知识范围。
- client：DeepSeek API客户端。
- model：当前使用的大语言模型名称。
- system_prompt：NPC固定角色提示词。
- affinity_level：NPC与玩家当前的好感度等级。
- affinity_score：NPC与玩家当前的好感度分数。
- affinity_style：当前好感度等级对应的回复风格。
- conversation_history：最近几轮工作记忆。
- retrieved_memories：检索到的可靠长期记忆。
- user_message：玩家本轮输入。
- final_user_message：组合长期记忆后的最终玩家消息。
- messages：最终发送给DeepSeek的消息列表。
- response：DeepSeek返回的完整响应对象。
- reply：NPC生成的回复文本。
"""

from openai import OpenAI

from relationship_models import AffinityLevel


# 不同好感度等级对应的回复风格。
#
# 好感度只影响语气、主动程度和交流深度，
# 不能改变事实、权限、安全边界和NPC身份。
AFFINITY_STYLE_PROMPTS: dict[AffinityLevel, str] = {
    "陌生": (
        "你刚认识这位玩家。"
        "保持礼貌和基本友善，但适当保持距离。"
        "回复自然简洁，不主动谈论私密话题。"
    ),
    "熟悉": (
        "你已经逐渐熟悉这位玩家。"
        "可以使用更加自然、放松的语气交流，"
        "偶尔主动提及与当前话题有关的信息。"
    ),
    "友好": (
        "你把这位玩家视为关系不错的朋友。"
        "回复可以更加热情和详细，"
        "愿意主动提供合理的帮助和建议。"
    ),
    "亲密": (
        "你非常信任并关心这位玩家。"
        "回复可以更加温暖、真诚，"
        "主动关心玩家当前的情况。"
        "但仍然必须遵守事实和安全边界。"
    ),
    "挚友": (
        "你把这位玩家视为非常重要的朋友。"
        "回复亲切、自然且真诚，"
        "可以更主动地联系可靠的共同记忆。"
        "但不能因此编造共同经历或泄露敏感信息。"
    ),
}


class NPC:
    """具有独立角色设定和回复能力的NPC。"""

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
        """初始化NPC基础资料和DeepSeek配置。"""

        # NPC唯一编号。
        self.npc_id = npc_id

        # NPC姓名。
        self.name = name

        # NPC身份或职业。
        self.role = role

        # NPC性格特点。
        self.personality = personality

        # NPC熟悉的知识领域。
        self.knowledge_scope = knowledge_scope

        # DeepSeek API客户端。
        self.client = client

        # 当前使用的大语言模型名称。
        self.model = model

        # 构建NPC固定角色提示词。
        self.system_prompt = self._build_system_prompt()

    def _build_system_prompt(self) -> str:
        """根据NPC资料构建固定角色系统提示词。"""

        # 固定提示词只描述NPC身份和基本规则。
        #
        # 好感度属于动态状态，
        # 会在每次generate_reply()时另外加入。
        return f"""
你是{self.name}，身份是{self.role}。

你的性格特点：
{self.personality}

你的知识范围：
{self.knowledge_scope}

基本对话要求：

1. 始终保持当前NPC身份，不要说自己是AI助手。
2. 使用自然、简洁的中文与玩家交流。
3. 回答必须符合你的职业、性格和知识范围。
4. 不知道的信息必须如实说明，不能随意编造。
5. 不要声称自己拥有没有被设定的权限或能力。

长期记忆规则：

1. 系统提供的长期记忆来自玩家过去的主动陈述，
   具有较高可信度。

2. 长期记忆与以前的NPC回答冲突时，
   必须以可靠长期记忆为准。

3. 只在长期记忆与当前问题有关时使用它。

4. 不要向玩家直接说出memory_key、相似度、
   综合分数等内部技术字段。

玩家个人事实规则：

1. 玩家姓名、身份、住址、编号、喜好、经历和关系等事实，
   只能来源于玩家亲口提供的信息，
   或系统明确提供的可靠长期记忆。

2. 历史中的assistant消息只是你以前的回答，
   不能作为玩家个人事实的可靠证据。

3. 如果没有可靠信息，必须明确表示不知道，
   不得自行补充玩家资料。

4. 不得编造玩家的住址、喜好、经历、关系和编号。

5. 密码、验证码、API密钥、银行卡号、身份证号等敏感信息，
   不得主动复述或泄露。

好感度规则：

1. 好感度只影响你的语气、交流深度和主动程度。
2. 好感度不能改变事实，也不能赋予你额外权限。
3. 好感度高不代表必须同意玩家的所有要求。
4. 不得因为好感度高而泄露敏感信息。
5. 不得编造你与玩家之间从未发生过的共同经历。
""".strip()

    def generate_reply(
        self,
        conversation_history: list[dict[str, str]],
        retrieved_memories: list[str],
        user_message: str,
        affinity_level: AffinityLevel = "陌生",
        affinity_score: int = 0,
    ) -> str:
        """结合记忆和好感度生成NPC回复。"""

        # 获取当前好感度等级对应的回复风格。
        affinity_style = AFFINITY_STYLE_PROMPTS.get(
            affinity_level,
            AFFINITY_STYLE_PROMPTS["陌生"],
        )

        # 构建本轮动态好感度提示词。
        relationship_prompt = f"""
你与当前玩家的关系状态：

- 好感度等级：{affinity_level}
- 好感度分数：{affinity_score}/100

当前回复风格：
{affinity_style}

请自然体现这种关系程度，
不要直接向玩家播报好感度数值或等级。
""".strip()

        # 首先放入固定NPC角色提示词。
        messages: list[dict[str, str]] = [
            {
                "role": "system",
                "content": self.system_prompt,
            },
            {
                "role": "system",
                "content": relationship_prompt,
            },
        ]

        # 加入最近几轮工作记忆。
        messages.extend(conversation_history)

        # 检索到长期记忆时，
        # 将可靠记忆与当前玩家问题一起发送。
        if retrieved_memories:
            memory_context = "\n".join(
                retrieved_memories
            )

            final_user_message = f"""
【可靠长期记忆】

{memory_context}

使用要求：

1. 仅在与当前问题相关时参考以上记忆。
2. 如果以前的NPC回答与可靠记忆冲突，以可靠记忆为准。
3. 不要向玩家展示记忆键、相似度和综合分数。
4. 不要补充可靠记忆中没有出现的玩家个人信息。

【玩家当前消息】

{user_message}
""".strip()

        else:
            # 没有检索到长期记忆时，
            # 只发送玩家当前消息。
            final_user_message = user_message

        # 将最终玩家消息加入消息列表。
        messages.append(
            {
                "role": "user",
                "content": final_user_message,
            }
        )

        # 调用DeepSeek生成NPC回复。
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
        )

        # 读取NPC回复内容。
        reply = response.choices[0].message.content

        # 防止模型返回空消息。
        if not reply:
            raise ValueError(
                f"NPC {self.name} 返回了空回复"
            )

        return reply