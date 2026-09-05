## NPC对话界面管理模块。
##
## 功能说明：
## 显示NPC资料、接收玩家输入、发送API请求并展示NPC回复。
## 每轮对话完成后显示当前关系、好感度和分数变化。
## 对话期间暂停玩家和当前NPC的移动。
##
## 主要变量含义：
## - panel：对话框主面板。
## - npc_name_label：显示NPC姓名的标签。
## - npc_title_label：显示NPC身份的标签。
## - dialogue_text：显示对话和好感度信息的富文本控件。
## - player_input：玩家输入框。
## - send_button：发送消息按钮。
## - close_button：关闭对话按钮。
## - current_npc_name：当前正在对话的NPC姓名。
## - api_client：全局APIClient节点。
## - dialogue_lines：当前对话框保存的显示内容。
## - request_in_progress：是否正在等待后端回复。

extends CanvasLayer


@onready var panel: Panel = $Panel
@onready var npc_name_label: Label = $Panel/NPCName
@onready var npc_title_label: Label = $Panel/NPCTitle
@onready var dialogue_text: RichTextLabel = $Panel/DialogueText
@onready var player_input: LineEdit = $Panel/PlayerInput
@onready var send_button: Button = $Panel/SendButton
@onready var close_button: Button = $Panel/CloseButton


var current_npc_name := ""
var api_client: Node = null
var dialogue_lines: Array[String] = []
var request_in_progress := false


func _ready() -> void:
	## 初始化对话界面和API信号。

	add_to_group("dialogue_system")
	visible = false

	send_button.pressed.connect(
		_on_send_button_pressed
	)
	close_button.pressed.connect(
		_on_close_button_pressed
	)
	player_input.text_submitted.connect(
		_on_text_submitted
	)

	api_client = get_node_or_null("/root/APIClient")

	if api_client != null:
		api_client.chat_response_received.connect(
			_on_chat_response_received
		)
		api_client.chat_error.connect(
			_on_chat_error
		)
		api_client.affinity_updated.connect(
			_on_affinity_updated
		)
	else:
		Config.log_error(
			"DialogueUI没有找到APIClient"
		)

	Config.log_info("对话UI初始化完成")


func _input(event: InputEvent) -> void:
	## 处理对话界面的键盘操作。

	if not visible:
		return

	if not event is InputEventKey:
		return

	if not event.pressed or event.echo:
		return

	if event.keycode == KEY_ESCAPE:
		hide_dialogue()
		get_viewport().set_input_as_handled()


func start_dialogue(npc_name: String) -> void:
	## 打开与指定NPC的对话界面。

	current_npc_name = npc_name
	request_in_progress = false

	var npc := get_npc_by_name(npc_name)

	if (
		npc != null
		and npc.has_method("set_interacting")
	):
		npc.set_interacting(true)

	npc_name_label.text = npc_name
	npc_title_label.text = Config.get_npc_title(
		npc_name
	)

	dialogue_lines.clear()
	dialogue_lines.append(
		"[color=gray]与 "
		+ _safe_text(npc_name)
		+ " 的对话开始……[/color]"
	)

	player_input.text = ""

	_set_request_state(false)
	_render_dialogue()
	show_dialogue()
	player_input.grab_focus()

	Config.log_info("开始对话：" + npc_name)


func show_dialogue() -> void:
	## 显示对话框并暂停玩家移动。

	visible = true

	var player := get_tree().get_first_node_in_group(
		"player"
	)

	if (
		player != null
		and player.has_method("set_interacting")
	):
		player.set_interacting(true)


func hide_dialogue() -> void:
	## 隐藏对话框并恢复玩家与NPC移动。

	visible = false
	request_in_progress = false
	_set_request_state(false)

	if not current_npc_name.is_empty():
		var npc := get_npc_by_name(
			current_npc_name
		)

		if (
			npc != null
			and npc.has_method("set_interacting")
		):
			npc.set_interacting(false)

	current_npc_name = ""

	var player := get_tree().get_first_node_in_group(
		"player"
	)

	if (
		player != null
		and player.has_method("set_interacting")
	):
		player.set_interacting(false)


func send_message() -> void:
	## 显示玩家消息并向FastAPI发送请求。

	if request_in_progress:
		return

	var message := player_input.text.strip_edges()

	if message.is_empty():
		return

	if current_npc_name.is_empty():
		Config.log_error("当前没有选择NPC")
		return

	if api_client == null:
		_on_chat_error("API客户端未找到")
		return

	dialogue_lines.append(
		"[color=cyan]玩家：[/color] "
		+ _safe_text(message)
	)

	player_input.text = ""
	request_in_progress = true

	_set_request_state(true)
	_render_dialogue()

	api_client.send_chat(
		current_npc_name,
		message
	)


func _on_send_button_pressed() -> void:
	## 处理发送按钮点击。

	send_message()


func _on_text_submitted(_text: String) -> void:
	## 处理输入框回车操作。

	send_message()


func _on_chat_response_received(
	npc_name: String,
	message: String,
) -> void:
	## 展示NPC回复。

	if npc_name != current_npc_name:
		return

	request_in_progress = false
	_set_request_state(false)

	dialogue_lines.append(
		"[color=yellow]"
		+ _safe_text(npc_name)
		+ "：[/color] "
		+ _safe_text(message)
	)

	_render_dialogue()
	player_input.grab_focus()


func _on_affinity_updated(
	npc_name: String,
	level: String,
	score: int,
	change: int,
) -> void:
	## 在NPC回复后显示好感度结果。

	if npc_name != current_npc_name:
		return

	var change_text := str(change)

	if change > 0:
		change_text = "+" + str(change)

	var level_text := level

	if level_text.is_empty():
		level_text = "未知"

	dialogue_lines.append(
		"[color=light_green]"
		+ "关系："
		+ _safe_text(level_text)
		+ "｜好感度："
		+ str(score)
		+ "/100"
		+ "｜本轮变化："
		+ change_text
		+ "[/color]"
	)

	_render_dialogue()


func _on_chat_error(
	error_message: String,
) -> void:
	## 展示对话请求错误。

	request_in_progress = false
	_set_request_state(false)

	dialogue_lines.append(
		"[color=red]错误："
		+ _safe_text(error_message)
		+ "[/color]"
	)

	_render_dialogue()

	if visible:
		player_input.grab_focus()


func _set_request_state(waiting: bool) -> void:
	## 设置等待回复时的输入框和按钮状态。

	send_button.disabled = waiting
	player_input.editable = not waiting


func _render_dialogue() -> void:
	## 重新绘制当前对话内容。

	dialogue_text.clear()

	for line in dialogue_lines:
		dialogue_text.append_text(line + "\n")

	if request_in_progress:
		dialogue_text.append_text(
			"[color=gray]"
			+ _safe_text(current_npc_name)
			+ "正在思考……[/color]\n"
		)

	dialogue_text.scroll_to_line(
		max(
			dialogue_text.get_line_count() - 1,
			0
		)
	)


func _safe_text(text: String) -> String:
	## 防止玩家输入被识别为BBCode。

	return text.replace(
		"[",
		"［"
	).replace(
		"]",
		"］"
	)


func _on_close_button_pressed() -> void:
	## 处理关闭按钮点击。

	hide_dialogue()


func get_npc_by_name(npc_name: String) -> Node:
	## 根据NPC姓名查找场景节点。

	var npcs := get_tree().get_nodes_in_group(
		"npcs"
	)

	for npc in npcs:
		if str(npc.get("npc_name")) == npc_name:
			return npc

	return null
