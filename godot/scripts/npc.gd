## NPC行为与玩家交互模块。
##
## 功能说明：
## 管理NPC姓名、身份、动画、随机巡逻、交互范围和状态显示。
## 玩家进入范围后可以按E打开对话界面。
##
## 主要变量含义：
## - npc_name：当前NPC的中文姓名。
## - npc_title：当前NPC的身份介绍。
## - sprite_frames：NPC使用的动画资源。
## - move_speed：NPC巡逻移动速度。
## - wander_enabled：是否允许NPC随机巡逻。
## - wander_range：NPC距离出生点的最大巡逻范围。
## - current_dialogue：NPC头顶显示的当前状态文字。
## - player：当前进入交互范围的玩家节点。
## - wander_target：NPC当前巡逻目标坐标。
## - wander_timer：下一次选择巡逻目标的倒计时。
## - is_wandering：NPC是否正在前往巡逻目标。
## - is_interacting：NPC是否正在和玩家对话。
## - spawn_position：NPC进入场景时的出生坐标。
## - dialogue_version：防止旧计时器隐藏较新的状态文字。

extends CharacterBody2D


@export var npc_name := "林舟"
@export var npc_title := "赛博小镇物资管理员"
@export var sprite_frames: SpriteFrames

@export var move_speed := 50.0
@export var wander_enabled := true
@export var wander_range := 200.0
@export var wander_interval_min := 3.0
@export var wander_interval_max := 8.0


var current_dialogue := ""
var interaction_hint: Label = null
var player: Node = null

var wander_target := Vector2.ZERO
var wander_timer := 0.0
var is_wandering := false
var is_interacting := false
var spawn_position := Vector2.ZERO
var dialogue_version := 0


@onready var animated_sprite: AnimatedSprite2D = get_node_or_null(
	"AnimatedSprite2D"
) as AnimatedSprite2D

@onready var interaction_area: Area2D = get_node_or_null(
	"InteractionArea"
) as Area2D

@onready var name_label: Label = get_node_or_null(
	"NameLabel"
) as Label

@onready var dialogue_label: Label = get_node_or_null(
	"DialogueLabel"
) as Label


func _ready() -> void:
	## 初始化NPC节点、交互区域和巡逻状态。

	add_to_group("npcs")

	interaction_hint = get_node_or_null(
		"InteractionHint"
	) as Label

	_refresh_identity_display()

	if interaction_area != null:
		interaction_area.body_entered.connect(_on_body_entered)
		interaction_area.body_exited.connect(_on_body_exited)
	else:
		Config.log_error(npc_name + "缺少InteractionArea节点")

	if dialogue_label != null:
		dialogue_label.text = ""
		dialogue_label.visible = false

	if interaction_hint != null:
		interaction_hint.text = "按E交互"
		interaction_hint.visible = false

	if sprite_frames != null and animated_sprite != null:
		animated_sprite.sprite_frames = sprite_frames

	_play_idle_animation()

	spawn_position = global_position

	if wander_enabled:
		wander_timer = randf_range(
			wander_interval_min,
			wander_interval_max
		)
		choose_new_wander_target()

	Config.log_info("NPC初始化：" + npc_name)


func configure(
	new_name: String,
	new_title: String,
) -> void:
	## 在主场景中重新配置NPC姓名和身份。

	npc_name = new_name
	npc_title = new_title
	_refresh_identity_display()

	Config.log_info(
		"NPC场景已配置为："
		+ npc_name
		+ "——"
		+ npc_title
	)


func _refresh_identity_display() -> void:
	## 刷新NPC头顶的姓名标签。

	if name_label != null:
		name_label.text = npc_name


func _on_body_entered(body: Node2D) -> void:
	## 玩家进入NPC交互范围。

	if not body.is_in_group("player"):
		return

	player = body

	if player.has_method("set_nearby_npc"):
		player.set_nearby_npc(self)

	show_interaction_hint()
	Config.log_info("玩家进入NPC范围：" + npc_name)


func _on_body_exited(body: Node2D) -> void:
	## 玩家离开NPC交互范围。

	if not body.is_in_group("player"):
		return

	if player != null and player.has_method("set_nearby_npc"):
		player.set_nearby_npc(null)

	player = null
	hide_interaction_hint()

	Config.log_info("玩家离开NPC范围：" + npc_name)


func show_interaction_hint() -> void:
	## 显示按E交互提示。

	if interaction_hint != null:
		interaction_hint.visible = true


func hide_interaction_hint() -> void:
	## 隐藏按E交互提示。

	if interaction_hint != null:
		interaction_hint.visible = false


func apply_status(status_data: Variant) -> void:
	## 读取FastAPI返回的NPC状态并更新头顶文字。

	if status_data is String:
		update_dialogue(status_data)
		return

	if not status_data is Dictionary:
		return

	var status: Dictionary = status_data

	# 后端返回的姓名字段是name。
	var received_name := str(
		status.get(
			"name",
			status.get("npc_name", "")
		)
	)

	if not received_name.is_empty():
		npc_name = received_name
		_refresh_identity_display()

	# 优先显示批量背景对话生成的台词。
	var text := str(
		status.get(
			"background_speech",
			status.get(
				"dialogue",
				status.get(
					"line",
					status.get("status_text", "")
				)
			)
		)
	)

	# 没有背景台词时，显示当前动作和情绪。
	if text.is_empty():
		var action := str(
			status.get(
				"current_action",
				status.get(
					"background_action",
					status.get("action", "")
				)
			)
		)

		var emotion := str(status.get("emotion", ""))

		if not action.is_empty() and not emotion.is_empty():
			text = action + "（" + emotion + "）"
		elif not action.is_empty():
			text = action
		elif not emotion.is_empty():
			text = emotion

	if not text.is_empty():
		update_dialogue(text)


func update_dialogue(dialogue: String) -> void:
	## 更新NPC头顶的状态文字，并在10秒后隐藏。

	current_dialogue = dialogue
	dialogue_version += 1

	var current_version := dialogue_version

	if dialogue_label == null:
		return

	dialogue_label.text = dialogue
	dialogue_label.visible = not dialogue.is_empty()

	if dialogue.is_empty():
		return

	await get_tree().create_timer(10.0).timeout

	# 只有没有更新过新内容时，才隐藏旧内容。
	if current_version == dialogue_version:
		dialogue_label.visible = false


func get_npc_name() -> String:
	## 返回当前NPC姓名。

	return npc_name


func get_npc_title() -> String:
	## 返回当前NPC身份。

	return npc_title


func _physics_process(delta: float) -> void:
	## 控制NPC随机巡逻和停止状态。

	if is_interacting:
		_stop_moving()
		return

	if not wander_enabled:
		_stop_moving()
		return

	wander_timer -= delta

	if wander_timer <= 0.0:
		choose_new_wander_target()
		wander_timer = randf_range(
			wander_interval_min,
			wander_interval_max
		)

	if not is_wandering:
		_stop_moving()
		return

	if global_position.distance_to(wander_target) < 10.0:
		is_wandering = false
		_stop_moving()
		return

	var direction := (
		wander_target - global_position
	).normalized()

	velocity = direction * move_speed
	move_and_slide()
	update_animation(direction)


func _stop_moving() -> void:
	## 停止NPC移动并播放待机动画。

	velocity = Vector2.ZERO
	move_and_slide()
	_play_idle_animation()


func choose_new_wander_target() -> void:
	## 在出生位置附近随机生成新的巡逻目标。

	var offset := Vector2(
		randf_range(-wander_range, wander_range),
		randf_range(-wander_range, wander_range)
	)

	wander_target = spawn_position + offset
	is_wandering = true

	Config.log_info(
		"NPC %s选择新目标：%s"
		% [npc_name, wander_target]
	)


func _play_idle_animation() -> void:
	## 播放NPC待机动画。

	if animated_sprite == null:
		return

	if animated_sprite.sprite_frames == null:
		return

	if animated_sprite.sprite_frames.has_animation("idle"):
		animated_sprite.play("idle")


func update_animation(direction: Vector2) -> void:
	## 根据NPC移动方向更新动画。

	if animated_sprite == null:
		return

	if animated_sprite.sprite_frames == null:
		return

	if direction.length() <= 0.0:
		_play_idle_animation()
		return

	if abs(direction.x) > abs(direction.y):
		if direction.x > 0.0:
			if animated_sprite.sprite_frames.has_animation(
				"walk_right"
			):
				animated_sprite.play("walk_right")
				animated_sprite.flip_h = false
			elif animated_sprite.sprite_frames.has_animation(
				"walk"
			):
				animated_sprite.play("walk")
				animated_sprite.flip_h = false
		else:
			if animated_sprite.sprite_frames.has_animation(
				"walk_left"
			):
				animated_sprite.play("walk_left")
				animated_sprite.flip_h = false
			elif animated_sprite.sprite_frames.has_animation(
				"walk"
			):
				animated_sprite.play("walk")
				animated_sprite.flip_h = true
	else:
		animated_sprite.flip_h = false

		if direction.y > 0.0:
			if animated_sprite.sprite_frames.has_animation(
				"walk_down"
			):
				animated_sprite.play("walk_down")
			elif animated_sprite.sprite_frames.has_animation(
				"walk"
			):
				animated_sprite.play("walk")
		else:
			if animated_sprite.sprite_frames.has_animation(
				"walk_up"
			):
				animated_sprite.play("walk_up")
			elif animated_sprite.sprite_frames.has_animation(
				"walk"
			):
				animated_sprite.play("walk")


func set_interacting(interacting: bool) -> void:
	## 设置NPC是否正在与玩家交互。

	is_interacting = interacting

	if interacting:
		hide_interaction_hint()
		_stop_moving()
		Config.log_info(npc_name + "进入交互状态")
	else:
		if player != null:
			show_interaction_hint()
		Config.log_info(npc_name + "退出交互状态")
