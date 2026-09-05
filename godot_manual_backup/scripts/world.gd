## 赛博小镇临时地图绘制脚本。
##
## 功能说明：
## 使用Godot绘图函数生成临时地图。
## 绘制草地、道路、网格和建筑区域，为玩家移动提供视觉参照。
##
## 主要变量含义：
## - MAP_SIZE：整个地图的宽度和高度。
## - GRID_SIZE：地图辅助网格之间的距离。
## - x：当前绘制的竖向网格坐标。
## - y：当前绘制的横向网格坐标。

extends Node2D


const MAP_SIZE := Vector2(1600.0, 900.0)
const GRID_SIZE := 100


func _draw() -> void:
	## 绘制地图背景、道路、网格和建筑。

	# 草地背景。
	draw_rect(
		Rect2(Vector2.ZERO, MAP_SIZE),
		Color("#5b8c5a"),
	)

	# 横向道路。
	draw_rect(
		Rect2(0.0, 350.0, MAP_SIZE.x, 200.0),
		Color("#59636e"),
	)

	# 纵向道路。
	draw_rect(
		Rect2(700.0, 0.0, 200.0, MAP_SIZE.y),
		Color("#59636e"),
	)

	# 地图辅助网格。
	for x in range(0, int(MAP_SIZE.x) + 1, GRID_SIZE):
		draw_line(
			Vector2(x, 0),
			Vector2(x, MAP_SIZE.y),
			Color(1.0, 1.0, 1.0, 0.08),
			1.0,
		)

	for y in range(0, int(MAP_SIZE.y) + 1, GRID_SIZE):
		draw_line(
			Vector2(0, y),
			Vector2(MAP_SIZE.x, y),
			Color(1.0, 1.0, 1.0, 0.08),
			1.0,
		)

	# 四块临时建筑区域。
	draw_rect(
		Rect2(100.0, 80.0, 350.0, 200.0),
		Color("#b86f52"),
	)
	draw_rect(
		Rect2(1100.0, 80.0, 350.0, 200.0),
		Color("#547aa5"),
	)
	draw_rect(
		Rect2(100.0, 620.0, 350.0, 200.0),
		Color("#d19a45"),
	)
	draw_rect(
		Rect2(1100.0, 620.0, 350.0, 200.0),
		Color("#775da6"),
	)
