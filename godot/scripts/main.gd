## Godot游戏主场景管理模块。
##
## 功能说明：
## 初始化三个NPC，将旧场景节点映射到新的NPC资料，
## 定时从FastAPI获取NPC状态，并把状态分发给对应NPC。
##
## 主要变量含义：
## - npc_lin_zhou：场景中用于显示林舟的NPC节点。
## - npc_wang_professor：场景中用于显示王教授的NPC节点。
## - npc_kangkang：场景中用于显示康康的NPC节点。
## - npc_nodes：NPC姓名到场景节点的映射。
## - api_client：全局APIClient节点。
## - status_update_timer：NPC状态刷新计时器。

extends Node2D


@onready var npc_lin_zhou: Node = get_node_or_null(
	"NPCs/NPC_Zhang"
)
@onready var npc_wang_professor: Node = get_node_or_null(
	"NPCs/NPC_Li"
)
@onready var npc_kangkang: Node = get_node_or_null(
	"NPCs/NPC_Wang"
)


var npc_nodes: Dictionary = {}
var api_client: Node = null
var status_update_timer := 0.0


func _ready() -> void:
	## 初始化NPC资料和API连接。

	Config.log_info("主场景初始化")

	_configure_npcs()

	api_client = get_node_or_null("/root/APIClient")

	if api_client == null:
		Config.log_error("APIClient未找到，请检查自动加载配置")
		return

	if not api_client.npc_status_received.is_connected(
		_on_npc_status_received
	):
		api_client.npc_status_received.connect(
			_on_npc_status_received
		)

	# 游戏启动后立即获取一次NPC状态。
	api_client.get_npc_status()


func _process(delta: float) -> void:
	## 按照配置的时间间隔刷新NPC状态。

	status_update_timer += delta

	if status_update_timer < Config.NPC_STATUS_UPDATE_INTERVAL:
		return

	status_update_timer = 0.0

	if api_client != null:
		api_client.get_npc_status()


func _configure_npcs() -> void:
	## 将旧场景里的三个NPC实例配置成当前项目NPC。

	_register_npc(
		npc_lin_zhou,
		"林舟",
		Config.get_npc_title("林舟")
	)

	_register_npc(
		npc_wang_professor,
		"王教授",
		Config.get_npc_title("王教授")
	)

	_register_npc(
		npc_kangkang,
		"康康",
		Config.get_npc_title("康康")
	)


func _register_npc(
	npc_node: Node,
	npc_name: String,
	npc_title: String,
) -> void:
	## 注册NPC节点并更新NPC显示信息。

	if npc_node == null:
		Config.log_error("场景中缺少NPC节点：" + npc_name)
		return

	npc_nodes[npc_name] = npc_node

	if npc_node.has_method("configure"):
		npc_node.configure(npc_name, npc_title)
	else:
		npc_node.set("npc_name", npc_name)
		npc_node.set("npc_title", npc_title)


func _on_npc_status_received(statuses: Dictionary) -> void:
	## 把后端NPC状态发送给对应场景节点。

	Config.log_info("更新NPC状态：" + str(statuses))

	for received_name in statuses:
		var npc_name := Config.get_npc_name(str(received_name))
		var npc_node := get_npc_node(npc_name)

		if npc_node == null:
			Config.log_error("找不到NPC场景节点：" + npc_name)
			continue

		var status_data: Variant = statuses[received_name]

		if npc_node.has_method("apply_status"):
			npc_node.apply_status(status_data)
		elif status_data is String and npc_node.has_method(
			"update_dialogue"
		):
			npc_node.update_dialogue(status_data)


func get_npc_node(npc_name: String) -> Node:
	## 根据NPC姓名返回对应场景节点。

	return npc_nodes.get(npc_name)
