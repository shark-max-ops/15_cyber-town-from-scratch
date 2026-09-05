## 玩家移动与NPC交互模块。
##
## 功能说明：
## 使用WASD或方向键控制玩家移动。
## 玩家进入NPC交互范围后，可以按E打开对话界面。
##
## 主要变量含义：
## - speed：玩家移动速度。
## - nearby_npc：当前位于交互范围内的NPC。
## - is_interacting：玩家是否正在与NPC对话。
## - animated_sprite：玩家动画节点。
## - camera：跟随玩家的摄像机。
## - interact_sound：开始交互时播放的音效。
## - running_sound：玩家移动时播放的音效。
## - is_playing_running_sound：走路音效是否正在播放。

extends CharacterBody2D


@export var speed := 200.0


var nearby_npc: Node = null
var is_interacting := false

var interact_sound: AudioStreamPlayer = null
var running_sound: AudioStreamPlayer = null
var is_playing_running_sound := false


@onready var animated_sprite: AnimatedSprite2D = get_node_or_null(
	"AnimatedSprite2D"
) as AnimatedSprite2D

@onready var camera: Camera2D = get_node_or_null(
	"Camera2D"
) as Camera2D


func _ready() -> void:
	## 初始化玩家分组、摄像机、动画和音效。

	add_to_group("player")

	speed = Config.PLAYER_SPEED

	interact_sound = get_node_or_null(
		"InteractSound"
	) as AudioStreamPlayer

	running_sound = get_node_or_null(
		"RunningSound"
	) as AudioStreamPlayer

	if camera != null:
		camera.enabled = true

	_play_idle_animation()
	Config.log_info("玩家初始化完成")


func _physics_process(_delta: float) -> void:
	## 读取键盘输入并移动玩家。

	if is_interacting:
		velocity = Vector2.ZERO
		move_and_slide()
		_play_idle_animation()
		stop_running_sound()
		return

	var input_direction := Input.get_vector(
		"ui_left",
		"ui_right",
		"ui_up",
		"ui_down"
	)

	# 即使项目没有单独配置move_*动作，也支持WASD。
	if Input.is_key_pressed(KEY_A):
		input_direction.x -= 1.0
	if Input.is_key_pressed(KEY_D):
		input_direction.x += 1.0
	if Input.is_key_pressed(KEY_W):
		input_direction.y -= 1.0
	if Input.is_key_pressed(KEY_S):
		input_direction.y += 1.0

	if input_direction.length() > 1.0:
		input_direction = input_direction.normalized()

	velocity = input_direction * speed
	move_and_slide()

	update_animation(input_direction)
	update_running_sound(input_direction)


func _unhandled_input(event: InputEvent) -> void:
	## 在没有被UI处理时检测E键交互。

	if is_interacting:
		return

	if not event is InputEventKey:
		return

	if not event.pressed or event.echo:
		return

	if (
		event.keycode == KEY_E
		or event.physical_keycode == KEY_E
	):
		if nearby_npc != null:
			interact_with_npc()
		else:
			Config.log_info("附近没有可以交互的NPC")


func interact_with_npc() -> void:
	## 通知对话系统开始与附近NPC对话。

	if nearby_npc == null:
		return

	if interact_sound != null:
		interact_sound.play()

	Config.log_info("与NPC交互：" + nearby_npc.npc_name)

	get_tree().call_group(
		"dialogue_system",
		"start_dialogue",
		nearby_npc.npc_name
	)


func set_nearby_npc(npc: Node) -> void:
	## 设置当前可交互NPC。

	nearby_npc = npc

	if nearby_npc != null:
		Config.log_info(
			"进入NPC范围："
			+ str(nearby_npc.npc_name)
		)
	else:
		Config.log_info("离开NPC范围")


func get_nearby_npc() -> Node:
	## 返回当前可交互NPC。

	return nearby_npc


func set_interacting(interacting: bool) -> void:
	## 设置玩家是否处于对话状态。

	is_interacting = interacting

	if interacting:
		velocity = Vector2.ZERO
		stop_running_sound()
		Config.log_info("玩家进入交互状态")
	else:
		Config.log_info("玩家退出交互状态")


func _play_idle_animation() -> void:
	## 播放待机动画。

	if animated_sprite == null:
		return

	if animated_sprite.sprite_frames == null:
		return

	if animated_sprite.sprite_frames.has_animation("idle"):
		animated_sprite.play("idle")


func update_animation(direction: Vector2) -> void:
	## 根据移动方向播放玩家动画。

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


func update_running_sound(direction: Vector2) -> void:
	## 根据玩家移动状态控制走路音效。

	if running_sound == null:
		return

	if direction.length() > 0.0:
		if not is_playing_running_sound:
			running_sound.play()
			is_playing_running_sound = true
	else:
		stop_running_sound()


func stop_running_sound() -> void:
	## 停止走路音效。

	if running_sound != null:
		running_sound.stop()

	is_playing_running_sound = false
