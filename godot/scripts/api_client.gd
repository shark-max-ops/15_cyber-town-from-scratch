## FastAPI后端通信模块。
##
## 功能说明：
## 向Python后端发送对话、NPC状态和NPC列表请求。
## 解析后端返回的JSON，并通过Godot信号传递结果。
##
## 主要变量含义：
## - chat_response_received：收到NPC回复时发出的信号。
## - chat_error：对话请求失败时发出的信号。
## - npc_status_received：收到NPC状态时发出的信号。
## - npc_list_received：收到NPC列表时发出的信号。
## - http_chat：处理对话请求的HTTPRequest节点。
## - http_status：处理NPC状态请求的HTTPRequest节点。
## - http_npcs：处理NPC列表请求的HTTPRequest节点。
## - current_chat_npc_name：当前正在等待回复的NPC姓名。
## - current_chat_npc_id：当前正在等待回复的NPC编号。

extends Node


signal chat_response_received(npc_name: String, message: String)
signal chat_error(error_message: String)
signal npc_status_received(dialogues: Dictionary)
signal npc_list_received(npcs: Array)


var http_chat: HTTPRequest
var http_status: HTTPRequest
var http_npcs: HTTPRequest

var current_chat_npc_name := ""
var current_chat_npc_id := ""


func _ready() -> void:
	## 初始化HTTP请求节点并连接完成信号。

	http_chat = HTTPRequest.new()
	http_status = HTTPRequest.new()
	http_npcs = HTTPRequest.new()

	add_child(http_chat)
	add_child(http_status)
	add_child(http_npcs)

	http_chat.request_completed.connect(_on_chat_request_completed)
	http_status.request_completed.connect(_on_status_request_completed)
	http_npcs.request_completed.connect(_on_npcs_request_completed)

	Config.log_info("API客户端初始化完成")


# ==================== 通用工具函数 ====================

func _parse_json_object(body_text: String) -> Dictionary:
	## 将响应文本解析为JSON字典。

	var json := JSON.new()
	var parse_result := json.parse(body_text)

	if parse_result != OK:
		Config.log_error("JSON解析失败：" + body_text)
		return {}

	if not json.data is Dictionary:
		Config.log_error("后端响应不是JSON对象：" + body_text)
		return {}

	return json.data


func _get_error_detail(
	response: Dictionary,
	fallback_message: String,
) -> String:
	## 从FastAPI错误响应中提取detail字段。

	if response.has("detail"):
		return str(response["detail"])

	return fallback_message


func _get_npc_name_from_data(npc_data: Dictionary) -> String:
	## 从NPC状态数据中取得中文姓名。

	var npc_name := str(
		npc_data.get(
			"npc_name",
			npc_data.get("name", ""),
		)
	)

	if not npc_name.is_empty():
		return npc_name

	var npc_id := str(npc_data.get("npc_id", ""))

	if not npc_id.is_empty():
		return Config.get_npc_name(npc_id)

	return ""


func _extract_npc_array(response: Dictionary) -> Array:
	## 兼容不同的NPC状态列表字段名称。

	if response.has("npcs") and response["npcs"] is Array:
		return response["npcs"]

	if response.has("statuses") and response["statuses"] is Array:
		return response["statuses"]

	if response.has("data") and response["data"] is Array:
		return response["data"]

	return []


# ==================== 对话API ====================

func send_chat(npc_name: String, message: String) -> void:
	## 给指定NPC发送一条玩家消息。

	var cleaned_message := message.strip_edges()

	if cleaned_message.is_empty():
		chat_error.emit("消息不能为空")
		return

	if http_chat.get_http_client_status() != HTTPClient.STATUS_DISCONNECTED:
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
		Config.log_error("发送对话请求失败，错误码：" + str(error))
		chat_error.emit("网络请求失败：" + str(error))


func _on_chat_request_completed(
	_result: int,
	response_code: int,
	_headers: PackedStringArray,
	body: PackedByteArray,
) -> void:
	## 处理后端返回的NPC对话结果。

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

	# 主要使用reply，同时兼容npc_reply和旧版message。
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
		Config.log_error("响应中没有找到NPC回复：" + body_text)
		chat_error.emit("NPC返回了空回复")
		return

	Config.log_info(
		"收到NPC回复："
		+ response_npc_name
		+ " -> "
		+ reply
	)

	chat_response_received.emit(response_npc_name, reply)


# ==================== NPC状态API ====================

func get_npc_status() -> void:
	## 获取所有NPC的当前状态。

	if http_status.get_http_client_status() != HTTPClient.STATUS_DISCONNECTED:
		Config.log_info("NPC状态请求正在处理中，跳过本次请求")
		return

	Config.log_api("GET /npcs/status")

	var error := http_status.request(Config.API_NPC_STATUS)

	if error != OK:
		Config.log_error("获取NPC状态失败，错误码：" + str(error))


func _on_status_request_completed(
	_result: int,
	response_code: int,
	_headers: PackedStringArray,
	body: PackedByteArray,
) -> void:
	## 将NPC状态转换成以NPC姓名为键的字典。

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

	# 兼容旧后端直接返回dialogues字典。
	if response.has("dialogues") and response["dialogues"] is Dictionary:
		var raw_dialogues: Dictionary = response["dialogues"]

		for key in raw_dialogues:
			var resolved_name := Config.get_npc_name(str(key))
			dialogues[resolved_name] = raw_dialogues[key]

	else:
		# 当前后端通常通过npcs或statuses数组返回。
		var npc_items := _extract_npc_array(response)

		for item in npc_items:
			if not item is Dictionary:
				continue

			var npc_data: Dictionary = item
			var npc_name := _get_npc_name_from_data(npc_data)

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
	## 通过NPC状态接口取得NPC列表。

	if http_npcs.get_http_client_status() != HTTPClient.STATUS_DISCONNECTED:
		Config.log_info("NPC列表请求正在处理中，跳过本次请求")
		return

	Config.log_api("GET /npcs/status")

	var error := http_npcs.request(Config.API_NPCS)

	if error != OK:
		Config.log_error("获取NPC列表失败，错误码：" + str(error))


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

	# 后端没有返回数组时，使用本地配置生成列表。
	if npcs.is_empty():
		for npc_name in Config.NPC_NAMES:
			npcs.append({
				"npc_id": Config.get_npc_id(npc_name),
				"npc_name": npc_name,
				"title": Config.get_npc_title(npc_name),
			})

	Config.log_info("收到NPC列表：" + str(npcs.size()) + "个NPC")
	npc_list_received.emit(npcs)
	
