"""
NPC好感度管理模块。

功能说明：
负责读取和保存玩家与NPC之间的好感度，
调用DeepSeek分析玩家态度，更新好感度分数，
计算关系等级，并限制重复消息刷取好感度。

主要变量含义：
- analyzer：玩家态度分析器。
- relationship_file：好感度JSON文件路径。
- relationships：全部玩家与NPC的好感度记录字典。
- npc_id：NPC唯一编号。
- player_id：玩家唯一编号。
- relationship_key：由npc_id和player_id组成的记录键。
- player_message：玩家本轮发送的消息。
- analysis：DeepSeek生成的玩家态度分析结果。
- applied_change：经过规则修正后实际应用的分数变化。
- message_hash：玩家消息经过SHA-256计算后的哈希值。
- duplicate_message：当前消息是否与近期消息重复。
- current_score：更新前的好感度分数。
- new_score：更新后的好感度分数。
- level：根据分数计算出的好感度等级。
"""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from pydantic import ValidationError

from affinity_analyzer import AffinityAnalyzer
from relationship_models import (
    AffinityLevel,
    RelationshipRecord,
    RelationshipUpdateResult,
)


# 当前项目根目录。
PROJECT_ROOT = Path(__file__).resolve().parent

# 默认好感度数据文件。
RELATIONSHIP_FILE = (
    PROJECT_ROOT
    / "data"
    / "relationships.json"
)

# 低于该置信度的分析结果不改变好感度。
MIN_ANALYSIS_CONFIDENCE = 0.55

# 每条记录最多保留10个近期消息哈希。
MAX_RECENT_MESSAGE_HASHES = 10


class RelationshipManager:
    """玩家与NPC之间的好感度管理器。"""

    def __init__(
        self,
        analyzer: AffinityAnalyzer,
        relationship_file: Path = RELATIONSHIP_FILE,
    ) -> None:
        """初始化好感度分析器和数据文件。"""

        # 玩家态度分析器。
        self.analyzer = analyzer

        # 好感度JSON文件路径。
        self.relationship_file = relationship_file

        # 加载已有好感度记录。
        self.relationships = self._load_relationships()

    def _load_relationships(
        self,
    ) -> dict[str, RelationshipRecord]:
        """从JSON文件读取全部好感度记录。"""

        # 文件不存在时使用空字典。
        if not self.relationship_file.exists():
            return {}

        try:
            # 读取原始JSON数据。
            with self.relationship_file.open(
                "r",
                encoding="utf-8",
            ) as file:
                raw_relationships = json.load(file)

            # JSON最外层必须是字典。
            if not isinstance(raw_relationships, dict):
                raise ValueError(
                    "好感度文件最外层必须是JSON对象"
                )

            relationships: dict[
                str,
                RelationshipRecord,
            ] = {}

            # 逐条使用Pydantic验证。
            for relationship_key, raw_record in (
                raw_relationships.items()
            ):
                try:
                    relationships[relationship_key] = (
                        RelationshipRecord.model_validate(
                            raw_record
                        )
                    )

                except ValidationError as error:
                    # 单条记录损坏时跳过，
                    # 不影响其他NPC的好感度。
                    print(
                        "[跳过格式错误的好感度记录："
                        f"{relationship_key}；{error}]"
                    )

            return relationships

        except (
            json.JSONDecodeError,
            OSError,
            ValueError,
        ) as error:
            # 整个文件损坏时使用空记录启动。
            print(f"[好感度文件读取失败：{error}]")
            return {}

    def _save_relationships(
        self,
    ) -> None:
        """把全部好感度记录保存到JSON文件。"""

        # data目录不存在时自动创建。
        self.relationship_file.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        # 将所有Pydantic对象转换成JSON兼容字典。
        save_data = {
            relationship_key: record.model_dump(
                mode="json"
            )
            for relationship_key, record
            in self.relationships.items()
        }

        # 使用UTF-8保存中文内容。
        with self.relationship_file.open(
            "w",
            encoding="utf-8",
        ) as file:
            json.dump(
                save_data,
                file,
                ensure_ascii=False,
                indent=2,
            )

    @staticmethod
    def _build_relationship_key(
        npc_id: str,
        player_id: str,
    ) -> str:
        """生成玩家与NPC之间的唯一关系键。"""

        # 使用双冒号分隔NPC和玩家编号。
        return f"{npc_id}::{player_id}"

    @staticmethod
    def _create_message_hash(
        player_message: str,
    ) -> str:
        """计算玩家消息的SHA-256哈希值。"""

        # 转换成小写并统一多余空格。
        normalized_message = " ".join(
            player_message.lower().split()
        )

        # 生成不可逆的消息哈希。
        return hashlib.sha256(
            normalized_message.encode("utf-8")
        ).hexdigest()

    @staticmethod
    def get_affinity_level(
        score: int,
    ) -> AffinityLevel:
        """根据好感度分数计算关系等级。"""

        # 0到20分为陌生。
        if score <= 20:
            return "陌生"

        # 21到40分为熟悉。
        if score <= 40:
            return "熟悉"

        # 41到60分为友好。
        if score <= 60:
            return "友好"

        # 61到80分为亲密。
        if score <= 80:
            return "亲密"

        # 81到100分为挚友。
        return "挚友"

    def get_relationship(
        self,
        npc_id: str,
        player_id: str = "default_player",
    ) -> RelationshipRecord:
        """取得玩家与指定NPC之间的好感度记录。"""

        # 创建该玩家与NPC之间的唯一键。
        relationship_key = self._build_relationship_key(
            npc_id=npc_id,
            player_id=player_id,
        )

        # 第一次互动时创建默认记录。
        if relationship_key not in self.relationships:
            self.relationships[relationship_key] = (
                RelationshipRecord(
                    npc_id=npc_id,
                    player_id=player_id,
                )
            )

        return self.relationships[relationship_key]

    def update_relationship(
        self,
        npc_id: str,
        player_message: str,
        player_id: str = "default_player",
    ) -> RelationshipUpdateResult:
        """分析玩家态度并更新指定NPC的好感度。"""

        # 获取当前好感度记录。
        relationship = self.get_relationship(
            npc_id=npc_id,
            player_id=player_id,
        )

        # 调用DeepSeek分析玩家态度。
        analysis = self.analyzer.analyze(
            player_message=player_message,
        )

        # 先使用DeepSeek建议的变化值。
        applied_change = analysis.score_change

        # 置信度过低时不改变好感度。
        if analysis.confidence < MIN_ANALYSIS_CONFIDENCE:
            applied_change = 0
            analysis.reason = (
                f"{analysis.reason}；分析置信度不足"
            )

        # 计算当前玩家消息哈希。
        message_hash = self._create_message_hash(
            player_message=player_message,
        )

        # 判断近期是否发送过相同消息。
        duplicate_message = (
            message_hash
            in relationship.recent_message_hashes
        )

        # 相同友好消息不能重复获得正分。
        #
        # 负面消息仍然扣分，避免通过重复辱骂绕过惩罚。
        if duplicate_message and applied_change > 0:
            applied_change = 0
            analysis.reason = (
                f"{analysis.reason}；近期重复消息不再加分"
            )

        # 高好感度阶段放慢正向增长速度。
        #
        # 避免玩家通过少量普通对话迅速达到挚友。
        if applied_change > 0:
            if relationship.score >= 80:
                applied_change = min(
                    applied_change,
                    1,
                )
            elif relationship.score >= 60:
                applied_change = min(
                    applied_change,
                    2,
                )

        # 保存更新前的分数。
        current_score = relationship.score

        # 将最终分数限制在0到100之间。
        new_score = max(
            0,
            min(
                100,
                current_score + applied_change,
            ),
        )

        # 更新好感度记录。
        relationship.score = new_score
        relationship.level = self.get_affinity_level(
            score=new_score,
        )
        relationship.interaction_count += 1
        relationship.last_change = applied_change
        relationship.last_reason = analysis.reason
        relationship.updated_at = datetime.now(
            timezone.utc
        )

        # 保存当前消息哈希。
        relationship.recent_message_hashes.append(
            message_hash
        )

        # 只保留最近指定数量的消息哈希。
        relationship.recent_message_hashes = (
            relationship.recent_message_hashes[
                -MAX_RECENT_MESSAGE_HASHES:
            ]
        )

        # 更新内存中的记录。
        relationship_key = self._build_relationship_key(
            npc_id=npc_id,
            player_id=player_id,
        )

        self.relationships[relationship_key] = relationship

        # 每轮互动后立即保存到JSON。
        self._save_relationships()

        # 返回完整更新结果。
        return RelationshipUpdateResult(
            relationship=relationship,
            analysis=analysis,
            applied_change=applied_change,
            duplicate_message=duplicate_message,
        )

