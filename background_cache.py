"""
background_cache.py

文件作用：
负责保存、读取和管理NPC批量背景对话缓存。

批量背景对话生成后会保存到JSON文件。
在缓存有效期内，程序直接读取JSON，不需要重复调用DeepSeek。
缓存过期后，程序可以重新生成一批背景对话。

主要类：
BackgroundDialogueCache：
背景对话缓存管理器，提供保存、读取、过期判断
和按NPC ID查询背景状态等功能。

主要变量：
PROJECT_ROOT：
当前项目根目录，也就是background_cache.py所在目录。
DEFAULT_CACHE_FILE：
默认缓存文件路径，位于data/background_dialogues.json。
DEFAULT_TTL_SECONDS：
默认缓存有效期，单位为秒，当前设置为300秒。
cache_file：
当前缓存管理器实际使用的JSON文件路径。
ttl_seconds：
当前缓存的有效时长。
generated_at：
一批背景对话生成并保存的时间。
scene_context：
生成背景对话时使用的场景描述。
result：
批量生成得到的全部NPC背景状态。
cache_record：
从JSON文件读取并验证后的完整缓存记录。
npc_id：
需要查询背景状态的NPC唯一编号。
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from pydantic import ValidationError

from background_models import (
    BackgroundDialogueCacheRecord,
    BatchBackgroundDialogueResult,
    NPCBackgroundDialogue,
)


# 当前项目根目录。
PROJECT_ROOT = Path(__file__).resolve().parent

# 默认背景对话缓存文件。
DEFAULT_CACHE_FILE = (
    PROJECT_ROOT
    / "data"
    / "background_dialogues.json"
)

# 默认缓存有效期为300秒，也就是5分钟。
DEFAULT_TTL_SECONDS = 300


class BackgroundDialogueCache:
    """NPC批量背景对话缓存管理器。"""

    def __init__(
        self,
        cache_file: Path = DEFAULT_CACHE_FILE,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
    ) -> None:
        """设置缓存文件位置和缓存有效期。"""

        # 保存当前缓存文件路径。
        self.cache_file = cache_file

        # 缓存有效期必须大于0秒。
        if ttl_seconds <= 0:
            raise ValueError("缓存有效期必须大于0秒")

        # 保存缓存有效期。
        self.ttl_seconds = ttl_seconds

    def save(
        self,
        scene_context: str,
        result: BatchBackgroundDialogueResult,
    ) -> None:
        """将一批背景对话保存到JSON缓存文件。"""

        # 创建完整缓存记录。
        cache_record = BackgroundDialogueCacheRecord(
            generated_at=datetime.now(timezone.utc),
            scene_context=scene_context,
            result=result,
        )

        # data目录不存在时自动创建。
        self.cache_file.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        # 将Pydantic对象转换成可以保存的字典。
        cache_data = cache_record.model_dump(
            mode="json",
        )

        # 使用UTF-8保存，确保中文正常显示。
        with self.cache_file.open(
            "w",
            encoding="utf-8",
        ) as file:
            json.dump(
                cache_data,
                file,
                ensure_ascii=False,
                indent=2,
            )

    def load(
        self,
    ) -> BackgroundDialogueCacheRecord | None:
        """读取并验证背景对话缓存。"""

        # 缓存文件不存在时返回None。
        if not self.cache_file.exists():
            return None

        try:
            # 从JSON文件读取原始字典。
            with self.cache_file.open(
                "r",
                encoding="utf-8",
            ) as file:
                cache_data = json.load(file)

            # 使用Pydantic验证缓存结构。
            return BackgroundDialogueCacheRecord.model_validate(
                cache_data
            )

        except (
            json.JSONDecodeError,
            ValidationError,
            OSError,
        ) as error:
            # 缓存损坏不应该导致整个程序退出。
            print(f"[背景对话缓存读取失败：{error}]")
            return None

    def is_expired(
        self,
        cache_record: BackgroundDialogueCacheRecord,
    ) -> bool:
        """判断指定缓存记录是否已经过期。"""

        # 获取缓存生成时间。
        generated_at = cache_record.generated_at

        # 兼容没有时区信息的旧版时间。
        if generated_at.tzinfo is None:
            generated_at = generated_at.replace(
                tzinfo=timezone.utc,
            )

        # 计算缓存已经存在了多少秒。
        cache_age_seconds = (
            datetime.now(timezone.utc)
            - generated_at
        ).total_seconds()

        # 超过有效期即视为过期。
        return cache_age_seconds >= self.ttl_seconds

    def load_valid(
        self,
    ) -> BackgroundDialogueCacheRecord | None:
        """读取尚未过期的有效缓存。"""

        # 先读取缓存文件。
        cache_record = self.load()

        # 没有缓存时直接返回None。
        if cache_record is None:
            return None

        # 缓存已经过期时返回None。
        if self.is_expired(cache_record):
            return None

        return cache_record

    def get_npc_dialogue(
        self,
        npc_id: str,
    ) -> NPCBackgroundDialogue | None:
        """从有效缓存中查找指定NPC的背景状态。"""

        # 只读取尚未过期的缓存。
        cache_record = self.load_valid()

        if cache_record is None:
            return None

        # 遍历全部NPC背景状态。
        for dialogue in cache_record.result.dialogues:
            # 找到对应NPC时立即返回。
            if dialogue.npc_id == npc_id:
                return dialogue

        # 缓存中不存在该NPC时返回None。
        return None

    def get_remaining_seconds(
        self,
        cache_record: BackgroundDialogueCacheRecord,
    ) -> int:
        """计算当前缓存还剩多少秒过期。"""

        # 获取缓存生成时间。
        generated_at = cache_record.generated_at

        # 兼容没有时区信息的时间。
        if generated_at.tzinfo is None:
            generated_at = generated_at.replace(
                tzinfo=timezone.utc,
            )

        # 计算缓存已经使用的秒数。
        cache_age_seconds = (
            datetime.now(timezone.utc)
            - generated_at
        ).total_seconds()

        # 剩余时间不能小于0。
        remaining_seconds = max(
            0,
            self.ttl_seconds - int(cache_age_seconds),
        )

        return remaining_seconds

