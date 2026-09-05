# 赛博小镇 Cyber Town

一个由Godot客户端和FastAPI后端组成的AI NPC小镇项目。

玩家可以在二维小镇中移动，与不同NPC交谈。NPC拥有独立人设、短期记忆、长期向量记忆、好感度和动态背景状态。

## 快速复现

### 1. 准备环境

运行本项目需要：

| 工具 | 建议版本 | 作用 |
|---|---|---|
| Git | 最新稳定版 | 克隆项目 |
| Python | 3.11 | 运行FastAPI后端 |
| uv | 最新稳定版 | 管理Python环境和依赖 |
| Godot | 4.5及以上 | 运行游戏客户端 |
| DeepSeek API Key | 有效密钥 | 调用大语言模型 |

本项目已经在以下环境中运行通过：

```text
Windows 11
Python 3.11
Godot 4.7.2
DeepSeek API
```

检查Python：

```powershell
python --version
```

预期显示：

```text
Python 3.11.x
```

如果没有安装uv，可以执行：

```powershell
python -m pip install uv
```

检查uv：

```powershell
uv --version
```

### 2. 克隆项目

打开PowerShell，进入准备存放项目的目录：

```powershell
cd D:\pyproject\agent
```

克隆项目：

```powershell
git clone https://github.com/shark-max-ops/15_cyber-town-from-scratch
```

进入项目根目录：

```powershell
cd 15-cyber-town-from-scratch
```

正确的项目根目录应当包含：

```text
api.py
pyproject.toml
uv.lock
godot/
```

如果没有使用Git，也可以在GitHub页面选择：

```text
Code → Download ZIP
```

下载并解压后，用VSCode打开项目根目录。

### 3. 安装Python依赖

在项目根目录运行：

```powershell
uv sync
```

uv会自动：

```text
读取pyproject.toml和uv.lock
→ 创建.venv虚拟环境
→ 安装FastAPI、OpenAI、Sentence Transformers等依赖
```

安装完成后，验证依赖：

```powershell
uv run python -c "import fastapi; import openai; import sentence_transformers; print('依赖安装成功')"
```

预期输出：

```text
依赖安装成功
```

### 4. 配置DeepSeek API

复制环境变量模板：

```powershell
Copy-Item .env.example .env
```

打开项目根目录中的`.env`，填写：

```env
LLM_API_KEY=你的DeepSeek_API密钥
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-v4-flash
```

例如：

```env
LLM_API_KEY=sk-xxxxxxxxxxxxxxxx
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-v4-flash
```

注意：

- 不要在密钥两侧添加引号；
- 不要在等号两侧添加空格；
- 不要将真实`.env`上传到GitHub；
- `.env.example`中不能填写真实密钥。

### 5. 启动FastAPI后端

在项目根目录运行：

```powershell
uv run uvicorn api:app --reload --host 127.0.0.1 --port 8000
```

第一次运行会加载Embedding模型：

```text
BAAI/bge-small-zh-v1.5
```

因此第一次启动可能需要等待模型下载。

如果看到：

```text
Warning: You are sending unauthenticated requests to the HF Hub
```

但程序仍继续加载，这只是没有配置Hugging Face Token的提醒，不影响正常使用。

启动成功后应看到：

```text
Application startup complete.
Uvicorn running on http://127.0.0.1:8000
```

不要关闭这个终端，Godot需要通过它访问AI后端。

### 6. 检查后端是否正常

打开浏览器访问：

```text
http://127.0.0.1:8000/health
```

如果能够看到JSON响应，说明后端已经启动。

API文档地址：

```text
http://127.0.0.1:8000/docs
```

NPC状态接口：

```text
http://127.0.0.1:8000/npcs/status
```

NPC状态接口应当返回三个NPC：

```text
lin_zhou
wang_professor
kang_kang
```

### 7. 导入Godot客户端

打开Godot项目管理器，点击：

```text
导入
```

选择项目中的：

```text
godot/project.godot
```

例如：

```text
D:\pyproject\agent\15-cyber-town-from-scratch\godot\project.godot
```

点击“导入并编辑”，等待Godot完成资源扫描。

### 8. 检查Godot配置

进入：

```text
项目 → 项目设置 → 全局
```

确认存在以下两个自动加载项：

```text
Config     res://scripts/config.gd
APIClient  res://scripts/api_client.gd
```

两项都必须启用，顺序应为：

```text
Config
APIClient
```

打开：

```text
res://scripts/config.gd
```

确认后端地址为：

```gdscript
const API_BASE_URL := "http://127.0.0.1:8000"
```

NPC编号应为：

```gdscript
const NPC_IDS := {
	"林舟": "lin_zhou",
	"王教授": "wang_professor",
	"康康": "kang_kang",
}
```

### 9. 运行完整项目

确保FastAPI终端仍然运行，然后回到Godot，打开：

```text
res://scenes/main.tscn
```

按：

```text
F5
```

如果Godot提示尚未设置主场景，选择：

```text
选择当前场景
```

正常情况下，FastAPI终端会出现：

```text
GET /background HTTP/1.1 200 OK
GET /npcs/status HTTP/1.1 200 OK
```

Godot输出面板会出现：

```text
[INFO] API客户端初始化完成
[INFO] 主场景初始化
[INFO] NPC背景状态加载成功
[INFO] 收到NPC状态更新：3个NPC
```

现在即可进入小镇并与NPC交谈。

### 10. 以后如何快速启动

首次配置完成后，以后只需要两步。

第一步，在项目根目录启动后端：

```powershell
uv run uvicorn api:app --reload --host 127.0.0.1 --port 8000
```

第二步，使用Godot打开：

```text
godot/project.godot
```

然后按`F5`运行游戏。

停止Godot游戏：

```text
F8
```

停止FastAPI：

```text
在FastAPI终端按Ctrl + C
```

## 主要功能

- Godot二维地图和玩家移动；
- 玩家靠近NPC后按E对话；
- 三个具有不同人设的AI NPC；
- DeepSeek生成符合人设的回复；
- 最近5轮工作记忆；
- JSON完整对话档案；
- 结构化长期记忆提取；
- Embedding语义检索；
- `memory_key`精确记忆查询；
- NPC独立记忆；
- NPC好感度系统；
- 好感度影响NPC回复语气；
- 批量生成NPC背景动作、情绪和台词；
- NPC背景缓存和手动刷新；
- FastAPI前后端接口；
- NPC并发状态保护；
- 对话日志和敏感信息基础脱敏。

## 项目结构

```text
15-cyber-town-from-scratch/
├── api.py                         # FastAPI入口和API路由
├── api_models.py                  # API请求与响应模型
├── application_context.py         # 后端组件统一初始化
├── dialogue_service.py            # 单轮NPC对话业务流程
│
├── config.py                      # Python环境配置
├── npc.py                         # NPC回复生成
├── npc_profiles.py                # NPC人设资料
├── agents.py                      # 多NPC统一管理
│
├── memory.py                      # 记忆读取、保存和检索
├── memory_models.py               # 长期记忆数据模型
├── memory_extractor.py            # DeepSeek长期记忆提取器
├── memory_query_planner.py        # 长期记忆查询规划器
├── migrate_memory.py              # 旧记忆迁移工具
│
├── affinity_analyzer.py           # 玩家态度分析
├── relationship_models.py         # 好感度数据模型
├── relationship_manager.py        # 好感度管理
│
├── background_models.py           # NPC背景状态模型
├── batch_dialogue.py              # 批量背景状态生成
├── background_cache.py            # 背景状态缓存
├── scene_context.py               # 动态小镇场景描述
│
├── state_models.py                # NPC运行状态模型
├── state_manager.py               # NPC状态和并发管理
├── dialogue_logger.py             # 对话日志
│
├── data/                          # 本地记忆与好感度数据
├── logs/                          # 本地运行日志
├── md/                            # 项目文档
│
├── godot/
│   ├── project.godot              # Godot项目配置
│   ├── scenes/
│   │   ├── main.tscn              # 游戏主场景
│   │   ├── player.tscn            # 玩家场景
│   │   ├── npc.tscn               # NPC通用场景
│   │   └── dialogue_ui.tscn       # 对话界面
│   ├── scripts/
│   │   ├── config.gd              # Godot全局配置
│   │   ├── api_client.gd          # FastAPI通信客户端
│   │   ├── main.gd                # 主场景管理
│   │   ├── player.gd              # 玩家移动与交互
│   │   ├── npc.gd                 # NPC行为
│   │   └── dialogue_ui.gd         # 对话界面逻辑
│   └── assets/                    # 图片、地图和音频资源
│
├── .env.example                   # 环境变量示例
├── .gitignore
├── pyproject.toml
└── uv.lock
```

## NPC列表

| npc_id | 姓名 | 身份 |
|---|---|---|
| `lin_zhou` | 林舟 | 赛博小镇物资管理员 |
| `wang_professor` | 王教授 | 图书馆管理员兼退休物理学教授 |
| `kang_kang` | 康康 | 赛博小镇居民和邮差老周的孩子 |

每个NPC拥有独立的：

- 对话档案；
- 工作记忆；
- 长期向量记忆；
- 好感度；
- 角色提示词；
- 运行状态。

## 技术栈

### Python后端

- Python 3.11
- FastAPI
- Uvicorn
- OpenAI兼容客户端
- DeepSeek API
- Pydantic
- Sentence Transformers
- `BAAI/bge-small-zh-v1.5`

### 游戏客户端

- Godot 4
- GDScript
- HTTPRequest
- CharacterBody2D
- Area2D
- CanvasLayer

## 游戏操作

| 按键 | 功能 |
|---|---|
| W/A/S/D | 玩家移动 |
| 方向键 | 玩家移动 |
| E | 与附近NPC交互 |
| Enter | 发送对话 |
| Esc | 关闭对话框 |
| R | 强制刷新全部NPC背景状态 |

按`R`会真实调用DeepSeek重新生成背景，不建议连续快速触发。

## 使用示例

靠近林舟，按`E`打开对话框，然后输入：

```text
你好，我叫陈文浩。
```

继续输入：

```text
我喜欢喝拿铁，请记住。
```

经过几轮对话后询问：

```text
我叫什么？我喜欢喝什么？
```

林舟会尝试从长期记忆中检索姓名和饮料偏好。

关闭并重新启动项目后再次询问。如果仍然能够回答，说明长期记忆持久化正常。

## 核心API

| 方法 | 路径 | 功能 |
|---|---|---|
| GET | `/health` | 检查后端运行状态 |
| GET | `/npcs/status` | 获取全部NPC状态 |
| GET | `/npcs/{npc_id}/status` | 获取单个NPC状态 |
| POST | `/dialogue` | 与NPC进行一轮对话 |
| GET | `/affinity/{npc_id}/{player_id}` | 查询好感度 |
| GET | `/background` | 获取或生成背景状态 |
| POST | `/background/refresh` | 强制刷新背景状态 |

对话请求示例：

```json
{
  "npc_id": "lin_zhou",
  "player_id": "default_player",
  "player_message": "你还记得我喜欢喝什么吗？"
}
```

## 记忆机制

每轮对话使用：

```text
NPC角色提示词
+ 最近5轮工作记忆
+ 查询规划器找到的长期记忆
+ 玩家当前消息
```

完整历史保存在JSON中，但不会全部发送给大模型。

长期记忆写入流程：

```text
玩家消息
→ DeepSeek提取记忆候选
→ 判断REMEMBER、FORGET或NONE
→ 生成结构化memory_key
→ 计算Embedding
→ 保存长期向量记忆
```

长期记忆查询流程：

```text
玩家问题
→ 查询规划器判断是否需要记忆
→ memory_key精确匹配
→ Embedding语义检索
→ 综合排序
→ 将相关记忆交给NPC
```

## 数据说明

以下目录默认不会上传GitHub：

```text
data/
logs/
```

它们可能包含：

- 玩家对话；
- 玩家偏好；
- NPC长期记忆；
- 好感度数据；
- 对话日志；
- 背景状态缓存。

删除这些文件会导致NPC失去相应记忆或关系数据。

## 常见问题

### FastAPI无法启动

确认当前终端位于项目根目录：

```powershell
Get-Location
```

然后重新同步依赖：

```powershell
uv sync
```

### 浏览器无法访问127.0.0.1:8000

确认FastAPI终端仍然显示：

```text
Uvicorn running on http://127.0.0.1:8000
```

如果已经停止，重新运行启动命令。

### 端口被占用

如果显示：

```text
Address already in use
```

说明8000端口已经有服务运行。

先打开：

```text
http://127.0.0.1:8000/health
```

如果可以访问，就不需要重复启动。

### Godot显示网络请求失败

检查：

- FastAPI是否正在运行；
- `API_BASE_URL`是否为`http://127.0.0.1:8000`；
- 浏览器能否打开`/health`；
- Windows防火墙是否阻止Godot联网。

### POST /dialogue返回422

正确请求字段是：

```text
npc_id
player_id
player_message
```

注意是`player_message`，不是`message`。

### 后端提示NPC不存在

三个正确编号是：

```text
lin_zhou
wang_professor
kang_kang
```

康康的编号是`kang_kang`，不是`kangkang`。

### Godot提示Unrecognized UID

关闭Godot，将：

```text
godot/.godot
```

重命名为：

```text
godot/.godot_old
```

重新打开项目，让Godot重建资源缓存。

## 当前限制

- 当前使用固定玩家编号`default_player`；
- 运行数据使用本地JSON保存；
- Embedding模型首次启动需要下载和加载；
- NPC巡逻尚未使用完整导航系统；
- Godot客户端主要连接本地FastAPI服务；
- 尚未实现登录、任务、背包和商店系统。

## 🚀 后续扩展方向

> **设计愿景**：目前的赛博小镇是单人游戏，但未来我们将构建一个动态、智能且高度沉浸式的虚拟世界。以下规划旨在打破单机界限，赋予 NPC 生命感与记忆，打造一个“活着的”赛博空间。

---

### 🌐 1. 多人在线支持
- **核心转变**：从单人体验升级为多人在线世界，允许多个玩家同时进入同一个办公室场景。
- **技术实现**：
  - 引入 **WebSocket** 协议实现玩家间的实时位置同步与动作广播。
  - 采用 **SQLite/PostgreSQL** 持久化玩家账户、背包及全局世界状态。
- **NPC 交互升级**：NPC 将具备**多玩家记忆**能力，针对不同玩家独立维护好感度与对话历史，实现“千人千面”的互动体验。

---

### 🎯 2. 任务系统
- **触发机制**：当玩家与特定 NPC 的好感度达到阈值时，自动解锁专属任务链。
- **任务示例**：
  - **张三（后端）**：请求协助调试一段崩溃的 Python 微服务代码。
  - **李四（产品）**：委托玩家收集 10 份用户体验反馈问卷。
  - **王五（设计）**：邀请玩家评价最新的 UI 原型稿。
- **奖励反馈**：完成任务可获得经验值、特殊道具或大量好感度加成，形成“互动→好感→任务→奖励”的核心循环。

---

### 🤖 3. NPC 之间的互动
- **生态模拟**：NPC 之间不再是孤立的个体，他们会在后台自动进行逻辑对话。
- **场景示例**：
  - 张三和李四在工位旁**讨论产品需求文档**的可行性。
  - 李四和王五就**界面交互逻辑**进行激烈的思维碰撞。
  - 王五向张三请教**前端动画性能优化**的技术细节。
- **玩家影响**：玩家可以驻足“偷听”这些对话，从中获取隐藏任务线索或世界观背景，让世界更具沉浸感。

---

### ❤️ 4. 情感系统
- **多维情绪**：在好感度基础上，引入**开心、难过、生气、兴奋、疲惫**等动态情绪状态。
- **表现差异**：
  - **心情愉悦时**：NPC 会主动分享额外信息，甚至赠送小礼物。
  - **心情低落时**：回复变得简短冷淡，交互难度增加。
- **动态变化**：情绪受 NPC 之间互动结果、玩家选择及随机事件影响，使每次登录都有新鲜感。

---

### 🎉 5. 动态事件系统
- **周期性活动**：增加世界活力，打破日常交互的平淡感。
- **事件类型**：
  - **团队会议**：所有 NPC 聚集在白板前讨论项目 sprint 计划，玩家可参与投票。
  - **生日派对**：为随机 NPC 举办庆祝活动，参与可获得限时增益 Buff。
  - **紧急故障**：服务器突然告警，需要全组（包括玩家）协作处理危机。
- **稀缺性**：事件为限时出现，错过需等待下一次周期刷新，提升游戏的收集与体验价值。

---

### 🗺️ 6. 更大的世界
- **场景扩展**：打破单一办公室限制，构建可探索的赛博街区。
- **新增场景**：
  - ☕ **赛博咖啡厅**：偶遇其他公司 NPC，获取行业八卦。
  - 📚 **未来图书馆**：查阅技术文档，获得技能提升线索。
  - 🌳 **数字公园**：进行放松小游戏，恢复 NPC 情绪值。
- **无缝移动**：玩家可在场景间自由穿梭，不同场景拥有独特的交互 NPC 和随机事件。

---

### 🧠 7. 个性化学习
- **AI 记忆沉淀**：NPC 会长期追踪并分析玩家的行为模式。
- **学习维度**：
  - **话题偏好**：若玩家频繁讨论 Python，NPC 会主动推送编程相关的科技新闻。
  - **时间习惯**：若玩家常在深夜登录，NPC 会切换至“夜话”模式，分享更私密或深沉的话题。
  - **交互风格**：适应玩家的对话长短句习惯，逐步调整自身的回复语气。
- **终极目标**：让 NPC 成为玩家在虚拟世界中的“老熟人”，而非冰冷的对话机器。

---

> 📌 **技术支撑**：以上所有扩展均需要底层架构支持。后续将引入 **专用向量数据库（如 Chroma/Milvus）** 实现长期记忆检索，并通过 **Godot 引擎导出部署** 实现跨平台游玩。**WebSocket 流式对话** 将保证多人在线时的即时响应体验。