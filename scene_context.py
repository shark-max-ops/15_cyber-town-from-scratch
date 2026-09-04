"""
赛博小镇场景上下文生成模块。

功能说明：
根据当前时间、星期、天气和特殊事件，
生成提供给批量背景对话生成器的场景描述。

当前阶段使用电脑本地时间。
后续接入Godot后，可以改为使用游戏世界中的虚拟时间。

主要变量含义：
- current_time：当前日期和时间。
- hour：当前小时，用于判断清晨、上午、下午或夜晚。
- weekday：当前星期名称。
- time_period：当前时间段名称。
- activity_hint：当前时间段适合发生的日常活动提示。
- weather：赛博小镇当前天气描述。
- special_event：当前正在发生的特殊事件。
- scene_context：最终提供给DeepSeek的完整场景描述。
"""

from datetime import datetime


# 星期数字到中文名称的映射。
WEEKDAY_NAMES = {
    0: "星期一",
    1: "星期二",
    2: "星期三",
    3: "星期四",
    4: "星期五",
    5: "星期六",
    6: "星期日",
}


def get_time_period(
    hour: int,
) -> tuple[str, str]:
    """根据小时返回时间段和活动提示。"""

    # 5点到8点属于清晨。
    if 5 <= hour < 8:
        return (
            "清晨",
            "小镇刚刚苏醒，居民开始准备一天的工作。",
        )

    # 8点到12点属于上午。
    if 8 <= hour < 12:
        return (
            "上午",
            "居民们正在认真工作，小镇各处逐渐忙碌起来。",
        )

    # 12点到14点属于中午。
    if 12 <= hour < 14:
        return (
            "中午",
            "大部分居民正在吃午饭或进行短暂休息。",
        )

    # 14点到18点属于下午。
    if 14 <= hour < 18:
        return (
            "下午",
            "小镇保持着稳定的工作节奏，街道上不时有人经过。",
        )

    # 18点到22点属于晚上。
    if 18 <= hour < 22:
        return (
            "晚上",
            "一天的工作逐渐结束，居民开始放松和交流。",
        )

    # 22点到第二天5点属于深夜。
    return (
        "深夜",
        "大部分居民已经休息，小镇变得安静，只剩少量灯光。",
    )


def build_scene_context(
    weather: str = "天气平稳",
    special_event: str | None = None,
    current_time: datetime | None = None,
) -> str:
    """生成当前赛博小镇的完整场景上下文。"""

    # 没有传入时间时，使用电脑当前本地时间。
    if current_time is None:
        current_time = datetime.now()

    # 提取当前小时。
    hour = current_time.hour

    # 根据小时取得时间段和活动提示。
    time_period, activity_hint = get_time_period(
        hour=hour,
    )

    # 将星期数字转换成中文星期名称。
    weekday = WEEKDAY_NAMES[
        current_time.weekday()
    ]

    # 格式化当前时间。
    formatted_time = current_time.strftime(
        "%Y年%m月%d日 %H:%M"
    )

    # 组合基础场景信息。
    scene_parts = [
        f"当前时间是{formatted_time}，{weekday}。",
        f"当前处于{time_period}。",
        f"天气情况：{weather}。",
        activity_hint,
        (
            "请根据NPC的职业、性格和当前时间，"
            "生成符合生活规律的背景状态。"
        ),
        (
            "不同NPC之间可以出现少量自然关联，"
            "但每个NPC仍然应该保持自己的身份特点。"
        ),
    ]

    # 存在特殊事件时加入场景描述。
    if special_event:
        scene_parts.append(
            f"当前特殊事件：{special_event}。"
        )

    # 将各部分组合成完整提示词。
    scene_context = "\n".join(scene_parts)

    return scene_context