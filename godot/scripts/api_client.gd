## FastAPI后端通信模块。
##
## 功能说明：
## 向Python后端发送NPC对话、NPC状态、NPC列表和背景状态请求。
## 解析后端返回的JSON，并通过Godot信号传递结果。
##
## 主要变量含义：
## - chat_response_received：收到NPC回复时发出的信号。
## - chat_error：对话请求失败时发出的信号。
## - affinity_updated：收到好感度数据时发出的信号。
## - npc_status_received：收到NPC状态时发出的信号。
## - npc_list_received：收到NPC列表时发出的信号。
## - background_loaded：背景状态加载成功时发出的信号。
## - background_error：背景状态加载失败时发出的信号。
## - http_chat：负责NPC对话请求的HTTPRequest节点。
## - http_status：负责NPC状态请求的HTTPRequest节点。
## - http_npcs：负责NPC列表请求的HTTPRequest节点。
## - http_background：负责NPC背景状态请求的HTTPRequest节点。
## - current_chat_npc_name：当前正在等待回复的NPC姓名。
## - current_chat_npc_id：当前正在等待回复的NPC编号。

extends Node


signal chat_response_received(npc_name: String, message: String)
signal chat_error(error_message: String)

signal affinity_updated(
	npc_name: String,
	level: String,
	score: int,
	change: int
)

signal npc_status_received(dialogues: Dictionary)
signal npc_list_received(npcs: Array)
signal background_loaded(scene_context: String)
signal background_error(error_message: String)


var http_chat: HTTPRequest
var http_status: HTTPRequest
var http_npcs: HTTPRequest
var http_background: HTTPRequest

var current_chat_npc_name := ""
var current_chat_npc_id := ""


func _ready() -> void:
	## 初始化所有HTTPRequest节点并连接完成信号。

	http_chat = HTTPRequest.new()
	http_status = HTTPRequest.new()
	http_npcs = HTTPRequest.new()
	http_background = HTTPRequest.new()

	add_child(http_chat)
	add_child(http_status)
	add_child(http_npcs)
	add_child(http_background)

	http_chat.request_completed.connect(
		_on_chat_request_completed
	)
	http_status.request_completed.connect(
		_on_status_request_completed
	)
	http_npcs.request_completed.connect(
		_on_npcs_request_completed
	)
	http_background.request_completed.connect(
		_on_background_request_completed
	)

	Config.log_info("API客户端初始化完成")


# ==================== 通用工具函数 ====================

func _parse_json_object(body_text: String) -> Dictionary:
	## 将后端响应文本解析为JSON字典。

	var json := JSON.new()
	var parse_result := json.parse(body_text)

	if parse_result != OK:
		Config.log_error("JSON解析失败：" + body_text)
		return {}

	if not json.data is Dictionary:
		Config.log_error("后端响应不是JSON对象：" + body_text)
		return {}

	return json.data as Dictionary


func _get_error_detail(
	response: Dictionary,
	fallback_message: String,
) -> String:
	## 从FastAPI错误响应中提取detail字段。

	if response.has("detail"):
		return str(response["detail"])

	return fallback_message


func _get_npc_name_from_data(
	npc_data: Dictionary,
) -> String:
	## 从NPC状态数据中读取中文姓名。

	var npc_name := str(
		npc_data.get(
			"npc_name",
			npc_data.get("name", "")
		)
	)

	if not npc_name.is_empty():
		return npc_name

	var npc_id := str(npc_data.get("npc_id", ""))

	if not npc_id.is_empty():
		return Config.get_npc_name(npc_id)

	return ""


func _extract_npc_array(
	response: Dictionary,
) -> Array:
	## 兼容后端可能使用的NPC列表字段名称。

	if response.has("npcs") and response["npcs"] is Array:
		return response["npcs"] as Array

	if (
		response.has("statuses")
		and response["statuses"] is Array
	):
		return response["statuses"] as Array

	if response.has("data") and response["data"] is Array:
		return response["data"] as Array

	return []


func _emit_affinity_if_present(
	response: Dictionary,
	npc_name: String,
) -> void:
	## 从对话响应中提取好感度数据并发出信号。

	var relationship: Dictionary = {}

	if (
		response.has("relationship")
		and response["relationship"] is Dictionary
	):
		relationship = response["relationship"] as Dictionary

	var score_value: Variant = response.get(
		"affinity_score",
		relationship.get("score", null)
	)

	# 没有返回好感度分数时不发出信号。
	if score_value == null:
		return

	var level := str(
		response.get(
			"affinity_level",
			relationship.get("level", "")
		)
	)

	var change_value: Variant = response.get(
		"affinity_change",
		relationship.get(
			"applied_change",
			relationship.get("change", 0)
		)
	)

	var score := int(score_value)
	var change := int(change_value)

	affinity_updated.emit(
		npc_name,
		level,
		score,
		change
	)


# ==================== 对话API ====================

func send_chat(
	npc_name: String,
	message: String,
) -> void:
	## 给指定NPC发送玩家消息。

	var cleaned_message := message.strip_edges()

	if cleaned_message.is_empty():
		chat_error.emit("消息不能为空")
		return

	if (
		http_chat.get_http_client_status()
		!= HTTPClient.STATUS_DISCONNECTED
	):
		chat_error.emit("上一条消息仍在处理中")
		return

	current_chat_npc_name = npc_name
	current_chat_npc_id = Config.get_npc_id(npc_name)

	var data := {
		"npc_id": current_chat_npc_id,
		"player_id": Config.DEFAULT_PLAYER_ID,
		"player_message": cleaned_message,
	}

	var headers := PackedStringArray([
		"Content-Type: application/json",
	])

	Config.log_api("POST /dialogue", data)

	var error := http_chat.request(
		Config.API_CHAT,
		headers,
		HTTPClient.METHOD_POST,
		JSON.stringify(data)
	)

	if error != OK:
		Config.log_error(
			"发送对话请求失败，错误码："
			+ str(error)
		)
		chat_error.emit("网络请求失败：" + str(error))


func _on_chat_request_completed(
	_result: int,
	response_code: int,
	_headers: PackedStringArray,
	body: PackedByteArray,
) -> void:
	## 处理FastAPI返回的NPC回复和好感度数据。

	var body_text := body.get_string_from_utf8()
	var response := _parse_json_object(body_text)

	if response_code < 200 or response_code >= 300:
		var error_message := _get_error_detail(
			response,
			"服务器错误：" + str(response_code)
		)

		Config.log_error(
			"对话请求失败，HTTP "
			+ str(response_code)
			+ "："
			+ error_message
		)

		chat_error.emit(error_message)
		return

	if response.is_empty():
		chat_error.emit("对话响应解析失败")
		return

	var reply := str(
		response.get(
			"reply",
			response.get(
				"npc_reply",
				response.get("message", "")
			)
		)
	)

	var response_npc_name := str(
		response.get(
			"npc_name",
			current_chat_npc_name
		)
	)

	if reply.is_empty():
		Config.log_error(
			"响应中没有找到NPC回复："
			+ body_text
		)
		chat_error.emit("NPC返回了空回复")
		return

	Config.log_info(
		"收到NPC回复："
		+ response_npc_name
		+ " -> "
		+ reply
	)

	# 先显示NPC回复，再显示本轮好感度。
	chat_response_received.emit(
		response_npc_name,
		reply
	)

	_emit_affinity_if_present(
		response,
		response_npc_name
	)


# ==================== 背景状态API ====================

func get_background(
	force_refresh: bool = false,
) -> void:
	## 获取NPC背景状态。
	## force_refresh为true时强制重新生成。

	if (
		http_background.get_http_client_status()
		!= HTTPClient.STATUS_DISCONNECTED
	):
		Config.log_info("背景状态请求正在处理中")
		return

	var request_url := Config.API_BACKGROUND
	var request_method := HTTPClient.METHOD_GET
	var endpoint_name := "GET /background"

	if force_refresh:
		request_url = Config.API_BACKGROUND_REFRESH
		request_method = HTTPClient.METHOD_POST
		endpoint_name = "POST /background/refresh"

	Config.log_api(endpoint_name)

	var headers := PackedStringArray([
		"Content-Type: application/json",
	])

	var error := http_background.request(
		request_url,
		headers,
		request_method
	)

	if error != OK:
		var error_message := (
			"发送背景状态请求失败，错误码："
			+ str(error)
		)

		Config.log_error(error_message)
		background_error.emit(error_message)


func _on_background_request_completed(
	_result: int,
	response_code: int,
	_headers: PackedStringArray,
	body: PackedByteArray,
) -> void:
	## 背景状态加载成功后获取最新NPC状态。

	var body_text := body.get_string_from_utf8()
	var response := _parse_json_object(body_text)

	if response_code < 200 or response_code >= 300:
		var error_message := _get_error_detail(
			response,
			"背景状态请求失败，HTTP "
			+ str(response_code)
		)

		Config.log_error(error_message)
		background_error.emit(error_message)
		return

	var scene_context := str(
		response.get(
			"scene_context",
			response.get(
				"scene",
				response.get("context", "")
			)
		)
	)

	Config.log_info("NPC背景状态加载成功")

	if not scene_context.is_empty():
		Config.log_info(
			"当前场景："
			+ scene_context
		)

	background_loaded.emit(scene_context)
	get_npc_status()


# ==================== NPC状态API ====================

func get_npc_status() -> void:
	## 获取所有NPC的当前状态。

	if (
		http_status.get_http_client_status()
		!= HTTPClient.STATUS_DISCONNECTED
	):
		Config.log_info(
			"NPC状态请求正在处理中，跳过本次请求"
		)
		return

	Config.log_api("GET /npcs/status")

	var error := http_status.request(
		Config.API_NPC_STATUS
	)

	if error != OK:
		Config.log_error(
			"获取NPC状态失败，错误码："
			+ str(error)
		)


func _on_status_request_completed(
	_result: int,
	response_code: int,
	_headers: PackedStringArray,
	body: PackedByteArray,
) -> void:
	## 将NPC状态转换为以NPC姓名为键的字典。

	var body_text := body.get_string_from_utf8()
	var response := _parse_json_object(body_text)

	if response_code < 200 or response_code >= 300:
		Config.log_error(
			"NPC状态请求失败，HTTP "
			+ str(response_code)
			+ "："
			+ _get_error_detail(response, body_text)
		)
		return

	if response.is_empty():
		return

	var dialogues: Dictionary = {}

	if (
		response.has("dialogues")
		and response["dialogues"] is Dictionary
	):
		var raw_dialogues := (
			response["dialogues"] as Dictionary
		)

		for key in raw_dialogues:
			var resolved_name := Config.get_npc_name(
				str(key)
			)
			dialogues[resolved_name] = raw_dialogues[key]

	else:
		var npc_items := _extract_npc_array(response)

		for item in npc_items:
			if not item is Dictionary:
				continue

			var npc_data := item as Dictionary
			var npc_name := _get_npc_name_from_data(
				npc_data
			)

			if not npc_name.is_empty():
				dialogues[npc_name] = npc_data

	Config.log_info(
		"收到NPC状态更新："
		+ str(dialogues.size())
		+ "个NPC"
	)

	npc_status_received.emit(dialogues)


# ==================== NPC列表API ====================

func get_npc_list() -> void:
	## 通过NPC状态接口获取NPC列表。

	if (
		http_npcs.get_http_client_status()
		!= HTTPClient.STATUS_DISCONNECTED
	):
		Config.log_info(
			"NPC列表请求正在处理中，跳过本次请求"
		)
		return

	Config.log_api("GET /npcs/status")

	var error := http_npcs.request(Config.API_NPCS)

	if error != OK:
		Config.log_error(
			"获取NPC列表失败，错误码："
			+ str(error)
		)


func _on_npcs_request_completed(
	_result: int,
	response_code: int,
	_headers: PackedStringArray,
	body: PackedByteArray,
) -> void:
	## 解析NPC列表请求结果。

	var body_text := body.get_string_from_utf8()
	var response := _parse_json_object(body_text)

	if response_code < 200 or response_code >= 300:
		Config.log_error(
			"NPC列表请求失败，HTTP "
			+ str(response_code)
			+ "："
			+ _get_error_detail(response, body_text)
		)
		return

	var npcs := _extract_npc_array(response)

	if npcs.is_empty():
		for npc_name in Config.NPC_NAMES:
			npcs.append({
				"npc_id": Config.get_npc_id(npc_name),
				"npc_name": npc_name,
				"title": Config.get_npc_title(npc_name),
			})

	Config.log_info(
		"收到NPC列表："
		+ str(npcs.size())
		+ "个NPC"
	)

	npc_list_received.emit(npcs)
