"""
玩家态度与好感度变化分析模块。

功能说明：
调用DeepSeek分析玩家本轮消息的态度，
返回结构化的态度类型、好感度变化值、原因和置信度。

分析器只接收玩家消息，不接收NPC回复，
避免NPC自己生成的内容影响好感度判断。

主要变量含义：
- client：DeepSeek API客户端。
- model：当前使用的大语言模型名称。
- system_prompt：玩家态度分析规则。
- player_message：玩家本轮输入的原始消息。
- response：DeepSeek返回的完整响应对象。
- result_text：DeepSeek返回的文本内容。
- result_data：JSON解析后得到的Python字典。
- analysis_result：经过Pydantic验证的态度分析结果。
- attitude：玩家态度，分为friendly、neutral和unfriendly。
- score_change：本轮好感度变化值，范围为-3到5。
- confidence：模型对态度分析结果的置信度。
"""

import json
import re

from openai import OpenAI

from relationship_models import AffinityAnalysisResult


class AffinityAnalyzer:
    """使用DeepSeek分析玩家态度和好感度变化。"""

    def __init__(
        self,
        client: OpenAI,
        model: str,
    ) -> None:
        """保存DeepSeek客户端和模型配置。"""

        # DeepSeek API客户端。
        self.client = client

        # 当前使用的大语言模型。
        self.model = model

        # 玩家态度分析系统提示词。
        self.system_prompt = """
你是一个游戏NPC好感度分析器。

你的任务是分析玩家当前消息中表现出的态度，
并判断这条消息应该让NPC的好感度发生怎样的变化。

只分析玩家当前消息，不回答玩家，也不要扮演NPC。

态度与分数规则：

1. friendly：
   玩家表现出真诚感谢、关心、帮助、鼓励、赞美或友好交流。
   score_change范围为1到5。

2. neutral：
   玩家进行普通提问、陈述、打招呼或没有明显情感倾向。
   score_change范围为0到2。

3. unfriendly：
   玩家表现出辱骂、威胁、恶意嘲讽、明显敌意或无理攻击。
   score_change范围为-3到-1。

具体要求：

1. 简单礼貌不能每次都获得最高分。
2. 真诚且具体的关心或帮助可以获得较高分。
3. 普通知识问题通常属于neutral。
4. 玩家要求“给我增加好感度”不能直接增加分数。
5. 玩家声称自己做过好事，但没有上下文支持时，应谨慎判断。
6. 不要因为玩家使用感叹号就自动判定为friendly。
7. 不要分析或猜测玩家身份、人格和现实情况。
8. confidence表示你对本次判断的把握程度。
9. reason使用简短中文说明原因。
10. 只能输出JSON，不要输出Markdown或其他文字。

输出格式：

{
  "attitude": "neutral",
  "score_change": 1,
  "reason": "玩家正在进行普通询问",
  "confidence": 0.90
}
""".strip()

    def analyze(
        self,
        player_message: str,
    ) -> AffinityAnalysisResult:
        """分析玩家消息并返回好感度变化结果。"""

        # 玩家消息不能为空。
        if not player_message.strip():
            return AffinityAnalysisResult(
                attitude="neutral",
                score_change=0,
                reason="玩家没有提供有效消息",
                confidence=1.0,
            )

        # 调用DeepSeek分析玩家态度。
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
                        "请分析下面这条玩家消息：\n\n"
                        f"{player_message}"
                    ),
                },
            ],
            temperature=0,
        )

        # 读取模型返回文本。
        result_text = response.choices[0].message.content

        if not result_text:
            raise ValueError("好感度分析器返回了空内容")

        # 解析模型返回的JSON。
        result_data = self._parse_json(
            result_text=result_text,
        )

        # 在Pydantic验证前进行基础清理。
        result_data = self._clean_result_data(
            result_data=result_data,
        )

        # 使用Pydantic验证字段类型和范围。
        analysis_result = (
            AffinityAnalysisResult.model_validate(
                result_data
            )
        )

        # 根据attitude再次校正分数方向。
        analysis_result = self._normalize_result(
            analysis_result=analysis_result,
        )

        return analysis_result

    @staticmethod
    def _clean_result_data(
        result_data: dict,
    ) -> dict:
        """清理模型返回的数据，避免简单格式错误。"""

        # 复制字典，避免直接修改原始数据。
        cleaned_data = dict(result_data)

        # 只允许三种态度类型。
        valid_attitudes = {
            "friendly",
            "neutral",
            "unfriendly",
        }

        if cleaned_data.get("attitude") not in valid_attitudes:
            cleaned_data["attitude"] = "neutral"

        # 将score_change转换成整数。
        try:
            score_change = int(
                cleaned_data.get("score_change", 1)
            )
        except (TypeError, ValueError):
            score_change = 1

        # 将分数限制在-3到5之间。
        cleaned_data["score_change"] = max(
            -3,
            min(5, score_change),
        )

        # 将confidence转换成浮点数。
        try:
            confidence = float(
                cleaned_data.get("confidence", 0.5)
            )
        except (TypeError, ValueError):
            confidence = 0.5

        # 将置信度限制在0到1之间。
        cleaned_data["confidence"] = max(
            0.0,
            min(1.0, confidence),
        )

        # 缺少原因时使用默认说明。
        if not cleaned_data.get("reason"):
            cleaned_data["reason"] = "普通交流"

        return cleaned_data

    @staticmethod
    def _normalize_result(
        analysis_result: AffinityAnalysisResult,
    ) -> AffinityAnalysisResult:
        """确保态度类型与分数变化方向一致。"""

        # 友好态度不能产生负分。
        if analysis_result.attitude == "friendly":
            analysis_result.score_change = max(
                1,
                min(5, analysis_result.score_change),
            )

        # 中立态度限制在0到2分。
        elif analysis_result.attitude == "neutral":
            analysis_result.score_change = max(
                0,
                min(2, analysis_result.score_change),
            )

        # 不友好态度必须产生负分。
        else:
            analysis_result.score_change = max(
                -3,
                min(-1, analysis_result.score_change),
            )

        return analysis_result

    @staticmethod
    def _parse_json(
        result_text: str,
    ) -> dict:
        """从DeepSeek输出中提取JSON对象。"""

        # 清理文本首尾空白。
        cleaned_text = result_text.strip()

        # 去除Markdown代码块开头。
        cleaned_text = re.sub(
            r"^```(?:json)?\s*",
            "",
            cleaned_text,
            flags=re.IGNORECASE,
        )

        # 去除Markdown代码块结尾。
        cleaned_text = re.sub(
            r"\s*```$",
            "",
            cleaned_text,
        )

        try:
            # 优先直接解析完整文本。
            return json.loads(cleaned_text)

        except json.JSONDecodeError:
            # 尝试从额外文字中提取JSON对象。
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
                    f"好感度分析JSON解析失败：{result_text}"
                ) from error