## 赛博小镇全局配置模块。
##
## 功能说明：
## 统一保存FastAPI接口地址、NPC资料、玩家配置和UI配置。
##
## 主要变量含义：
## - API_BASE_URL：FastAPI后端基础地址。
## - API_CHAT：NPC对话接口地址。
## - API_NPC_STATUS：NPC状态接口地址。
## - API_NPCS：NPC列表使用的接口地址。
## - DEFAULT_PLAYER_ID：当前Godot客户端的玩家编号。
## - NPC_NAMES：三个NPC的中文姓名。
## - NPC_IDS：NPC姓名与后端npc_id的映射。
## - NPC_TITLES：NPC姓名与身份介绍的映射。
## - PLAYER_SPEED：玩家移动速度。
## - INTERACTION_DISTANCE：玩家与NPC的交互距离。
## - NPC_STATUS_UPDATE_INTERVAL：NPC状态刷新间隔。
## - DIALOGUE_FADE_TIME：对话框动画时间。
## - NPC_LABEL_OFFSET：NPC姓名标签偏移。
## - DEBUG_MODE：是否输出调试日志。
## - SHOW_INTERACTION_RANGE：是否显示交互范围。

extends Node


# ==================== API配置 ====================

const API_BASE_URL := "http://127.0.0.1:8000"
const API_CHAT := API_BASE_URL + "/dialogue"
const API_NPC_STATUS := API_BASE_URL + "/npcs/status"

# 当前后端没有单独的GET /npcs接口，
# 因此NPC列表暂时从状态接口中取得。
const API_NPCS := API_NPC_STATUS

const DEFAULT_PLAYER_ID := "default_player"


# ==================== NPC配置 ====================

const NPC_NAMES := [
	"林舟",
	"王教授",
	"康康",
]

const NPC_IDS := {
	"林舟": "lin_zhou",
	"王教授": "wang_professor",
	"康康": "kang_kang",
}

const NPC_TITLES := {
	"林舟": "赛博小镇物资管理员",
	"王教授": "赛博小镇图书馆管理员兼退休物理学教授",
	"康康": "赛博小镇居民和邮差老周的孩子",
}


# ==================== 游戏配置 ====================

const PLAYER_SPEED := 200.0
const INTERACTION_DISTANCE := 80.0
const NPC_STATUS_UPDATE_INTERVAL := 30.0


# ==================== UI配置 ====================

const DIALOGUE_FADE_TIME := 0.3
const NPC_LABEL_OFFSET := Vector2(0, -60)


# ==================== 调试配置 ====================

const DEBUG_MODE := true
const SHOW_INTERACTION_RANGE := true


# ==================== NPC转换函数 ====================

func get_npc_id(npc_name: String) -> String:
	## 根据NPC中文姓名返回后端使用的npc_id。

	return str(NPC_IDS.get(npc_name, npc_name))


func get_npc_name(npc_id: String) -> String:
	## 根据后端npc_id返回NPC中文姓名。

	for npc_name in NPC_IDS:
		if str(NPC_IDS[npc_name]) == npc_id:
			return str(npc_name)

	return npc_id


func get_npc_title(npc_name: String) -> String:
	## 根据NPC姓名返回身份介绍。

	return str(NPC_TITLES.get(npc_name, ""))


# ==================== 日志函数 ====================

func log_info(message: String) -> void:
	## 输出普通调试信息。

	if DEBUG_MODE:
		print("[INFO] ", message)


func log_error(message: String) -> void:
	## 输出错误信息。

	print("[ERROR] ", message)


func log_api(endpoint: String, data: Dictionary = {}) -> void:
	## 输出API请求信息。

	if not DEBUG_MODE:
		return

	if data.is_empty():
		print("[API] ", endpoint)
	else:
		print("[API] ", endpoint, " -> ", JSON.stringify(data))
