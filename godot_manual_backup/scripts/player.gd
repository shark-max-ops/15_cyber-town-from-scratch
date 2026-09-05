## 玩家移动控制脚本。
##
## 功能说明：
## 读取WASD或方向键输入。
## 控制玩家在二维场景中移动并处理物理碰撞。
##
## 主要变量含义：
## - move_speed：玩家每秒移动的像素距离。
## - input_direction：玩家当前输入的二维移动方向。
## - velocity：CharacterBody2D内置的移动速度变量。

extends CharacterBody2D


@export var move_speed: float = 220.0


func _physics_process(_delta: float) -> void:
	## 每个物理帧读取输入并移动玩家。

	var input_direction := Input.get_vector(
		"move_left",
		"move_right",
		"move_up",
		"move_down",
	)

	velocity = input_direction * move_speed
	move_and_slide()
