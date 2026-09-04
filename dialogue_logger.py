"""
NPC对话日志记录模块。

功能说明：
负责记录玩家与NPC的每轮对话、长期记忆检索结果、
好感度变化、NPC状态变化和程序错误。

日志使用JSON Lines格式保存，每行是一个完整JSON对象，
方便人工查看，也方便后续使用Python进行统计分析。

主要变量含义：
- log_dir：日志文件保存目录。
- log_lock：保护日志写入操作的线程锁。
- event：日志事件类型。
- timestamp：日志记录时间。
- npc_id：NPC唯一编号。
- npc_name：NPC姓名。
- player_id：玩家唯一编号。
- player_message：经过脱敏后的玩家消息。
- npc_reply：经过脱敏后的NPC回复。
- retrieved_memories：本轮检索到的长期记忆。
- relationship_update：本轮对话产生的好感度更新结果。
- previous_score：更新前的好感度分数。
- log_record：最终写入JSONL文件的日志字典。
- log_file：根据当前日期生成的日志文件路径。
- context：发生错误时的功能位置说明。
- error：捕获到的异常对象。
"""

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any

from relationship_models import RelationshipUpdateResult


# 当前项目根目录。
PROJECT_ROOT = Path(__file__).resolve().parent

# 默认日志保存目录。
DEFAULT_LOG_DIR = PROJECT_ROOT / "logs"


class DialogueLogger:
    """赛博小镇对话与运行事件日志记录器。"""

    def __init__(
        self,
        log_dir: Path = DEFAULT_LOG_DIR,
    ) -> None:
        """初始化日志目录和线程锁。"""

        # 保存日志目录路径。
        self.log_dir = log_dir

        # 日志目录不存在时自动创建。
        self.log_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        # 防止多个请求同时写入日志造成内容交错。
        self.log_lock = RLock()

    def _get_log_file(
        self,
    ) -> Path:
        """根据当前日期生成日志文件路径。"""

        # 使用本地日期生成每日独立日志文件。
        current_date = datetime.now().strftime(
            "%Y-%m-%d"
        )

        # 日志文件示例：
        # logs/dialogue_2026-09-03.jsonl
        return (
            self.log_dir
            / f"dialogue_{current_date}.jsonl"
        )

    @staticmethod
    def _sanitize_text(
        text: str,
    ) -> str:
        """对日志文本中的常见敏感信息进行基础脱敏。"""

        # 复制原始文本，后续在副本上进行替换。
        sanitized_text = text

        # 隐藏常见sk-格式API密钥。
        sanitized_text = re.sub(
            r"\bsk-[A-Za-z0-9_-]{8,}\b",
            "[API密钥已隐藏]",
            sanitized_text,
            flags=re.IGNORECASE,
        )

        # 隐藏密码、验证码、密钥和Token后面的值。
        sensitive_value_pattern = (
            r"("
            r"密码(?:编号)?"
            r"|验证码"
            r"|API[_\s-]?KEY"
            r"|API密钥"
            r"|access[_\s-]?token"
            r"|token"
            r"|银行卡号"
            r"|身份证号"
            r")"
            r"(\s*(?:是|为|：|:|=)?\s*)"
            r"([A-Za-z0-9_-]{4,})"
        )

        sanitized_text = re.sub(
            sensitive_value_pattern,
            r"\1\2[敏感内容已隐藏]",
            sanitized_text,
            flags=re.IGNORECASE,
        )

        return sanitized_text

    #归遍历任意嵌套的字典、列表和字符串，仅对内部所有字符串执行敏感信息替换脱敏
    def _sanitize_value(
        self,
        value: Any,
    ) -> Any:
        """递归脱敏字符串、列表和字典中的内容。"""

        # 字符串直接执行敏感信息替换。
        if isinstance(value, str):
            return self._sanitize_text(value)

        # 列表中的每个元素分别脱敏。
        if isinstance(value, list):
            return [
                self._sanitize_value(item)
                for item in value
            ]

        # 字典中的每个值分别脱敏。
        if isinstance(value, dict):
            return {
                key: self._sanitize_value(item)
                for key, item in value.items()
            }

        # 数字、布尔值和None不需要处理。
        return value

    def _write_record(
        self,
        log_record: dict[str, Any],
    ) -> None:
        """将一条日志记录安全写入JSONL文件。"""

        # 对整条日志进行递归脱敏。
        sanitized_record = self._sanitize_value(
            log_record
        )

        # 获取当天的日志文件。
        log_file = self._get_log_file()

        # 使用锁保证每行日志完整写入。
        with self.log_lock:
            with log_file.open(
                "a",
                encoding="utf-8",
            ) as file:
                # JSONL每条记录单独占一行。
                file.write(
                    json.dumps(
                        sanitized_record,
                        ensure_ascii=False,
                    )
                    + "\n"
                )

    def log_dialogue(
        self,
        npc_id: str,
        npc_name: str,
        player_id: str,
        player_message: str,
        npc_reply: str,
        retrieved_memories: list[str],
        relationship_update: (
            RelationshipUpdateResult | None
        ),
        previous_score: int,
    ) -> None:
        """记录一轮完整的玩家与NPC对话。"""

        # 没有好感度更新结果时使用空信息。
        if relationship_update is None:
            affinity_data = {
                "previous_score": previous_score,
                "new_score": previous_score,
                "applied_change": 0,
                "level": None,
                "attitude": None,
                "confidence": None,
                "reason": "好感度更新失败",
            }

        else:
            # 整理本轮好感度变化信息。
            affinity_data = {
                "previous_score": previous_score,
                "new_score": (
                    relationship_update
                    .relationship
                    .score
                ),
                "applied_change": (
                    relationship_update.applied_change
                ),
                "level": (
                    relationship_update
                    .relationship
                    .level
                ),
                "attitude": (
                    relationship_update
                    .analysis
                    .attitude
                ),
                "confidence": (
                    relationship_update
                    .analysis
                    .confidence
                ),
                "reason": (
                    relationship_update
                    .analysis
                    .reason
                ),
                "duplicate_message": (
                    relationship_update
                    .duplicate_message
                ),
            }

        # 构造完整对话日志。
        log_record = {
            "timestamp": datetime.now(
                timezone.utc
            ).isoformat(),
            "event": "dialogue",
            "npc_id": npc_id,
            "npc_name": npc_name,
            "player_id": player_id,
            "player_message": player_message,
            "npc_reply": npc_reply,
            "retrieved_memories": retrieved_memories,
            "affinity": affinity_data,
        }

        # 写入每日JSONL日志文件。
        self._write_record(
            log_record=log_record,
        )

        # 控制台只显示简短提示，
        # 避免把完整对话重复打印一次。
        print(
            f"[对话日志已保存："
            f"{self._get_log_file().name}]"
        )

    def log_state_change(
        self,
        npc_id: str,
        previous_status: str,
        new_status: str,
        player_id: str | None = None,
    ) -> None:
        """记录NPC运行状态变化。"""

        # 构造NPC状态变化日志。
        log_record = {
            "timestamp": datetime.now(
                timezone.utc
            ).isoformat(),
            "event": "state_change",
            "npc_id": npc_id,
            "player_id": player_id,
            "previous_status": previous_status,
            "new_status": new_status,
        }

        # 写入日志文件。
        self._write_record(
            log_record=log_record,
        )

    def log_error(
        self,
        context: str,
        error: Exception,
        npc_id: str | None = None,
        player_id: str | None = None,
    ) -> None:
        """记录程序运行过程中捕获到的错误。"""

        # 构造错误日志。
        log_record = {
            "timestamp": datetime.now(
                timezone.utc
            ).isoformat(),
            "event": "error",
            "context": context,
            "error_type": type(error).__name__,
            "error_message": str(error),
            "npc_id": npc_id,
            "player_id": player_id,
        }

        # 写入日志文件。
        self._write_record(
            log_record=log_record,
        )

        # 在控制台显示错误提示。
        print(
            f"[错误日志已保存："
            f"{context}；{error}]"
        )
