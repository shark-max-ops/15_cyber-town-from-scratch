"""
赛博小镇FastAPI后端入口模块。

功能说明：
创建FastAPI应用，在服务启动时初始化赛博小镇全部组件，
配置跨域访问，并提供后端健康检查接口。

主要变量含义：
- app：赛博小镇FastAPI应用对象。
- application_context：全部核心组件的统一容器。
- lifespan：FastAPI服务的启动和关闭生命周期函数。
- npc_count：当前已经初始化的NPC数量。
- ALLOWED_ORIGINS：允许访问后端的前端来源列表。
- API_VERSION：当前后端接口版本号。
- background_generation_lock：防止并发请求重复生成背景对话。
- force_refresh：是否强制忽略当前背景缓存。
- cache_record：读取到的背景对话缓存记录。
- scene_context：根据当前时间生成的小镇场景描述。
- dialogue_service：处理一轮完整NPC对话的业务服务。
- request：经过Pydantic验证的玩家对话请求。
- dialogue_result：NPC单轮对话处理结果。
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager  #用于定义异步上下文管理器

# FastAPI用于创建应用，HTTPException用于返回HTTP错误。
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

# 导入API请求与响应数据模型。
from api_models import (
    AffinityResponse,
    BackgroundDialogueResponse,
    DialogueRequest,
    DialogueResponse,
    HealthResponse,
    NPCStatusListResponse,
)
# 导入单个NPC状态模型。
from state_models import NPCState
from application_context import application_context
# asyncio用于把同步的DeepSeek请求放入工作线程，
# 避免阻塞FastAPI事件循环。
import asyncio
# 导入动态场景上下文生成函数。
from scene_context import build_scene_context

# 导入单轮对话服务和业务异常。
from dialogue_service import (
    DialogueService,
    NPCBusyError,
    NPCNotFoundError,
)

# 当前后端接口版本。
API_VERSION = "1.0.0"

# 开发阶段允许所有来源访问后端。
#
# 正式部署后应该修改成具体的前端地址。
ALLOWED_ORIGINS = ["*"]
# 背景对话生成锁。
#
# 防止多个HTTP请求同时发现缓存过期，
# 然后重复调用DeepSeek生成相同内容。
background_generation_lock = asyncio.Lock()

# 创建单轮对话业务服务。
#
# 此时只是保存application_context引用，
# 不会立即调用DeepSeek或加载Embedding模型。
dialogue_service = DialogueService(
    context=application_context,
)

@asynccontextmanager
async def lifespan(
    _app: FastAPI,
) -> AsyncGenerator[None, None]:
    """管理FastAPI服务的启动和关闭流程。"""

    print("=" * 60)
    print("赛博小镇后端服务正在启动……")
    print("=" * 60)

    # try/finally可以保证：
    #
    # 正常关闭、Ctrl+C、Uvicorn重新加载时，
    # 都会尽量执行application_context.shutdown()。
    try:
        # 初始化DeepSeek、Embedding、Qdrant、
        # NPC、记忆、好感度、状态和日志组件。
        application_context.initialize()

        print("=" * 60)
        print("赛博小镇后端服务启动成功")
        print("=" * 60)

        # yield之后FastAPI开始接收请求。
        yield

    finally:
        print("=" * 60)
        print("赛博小镇后端服务正在关闭……")
        print("=" * 60)

        # 关闭Qdrant和LLM客户端，
        # 避免本地数据库文件锁没有及时释放。
        application_context.shutdown()

        print("=" * 60)
        print("赛博小镇后端服务已经关闭")
        print("=" * 60)

# 创建FastAPI应用。
app = FastAPI(
    title="赛博小镇后端服务",
    description=(
        "拥有NPC对话、记忆、好感度和状态系统的"
        "AI小镇后端"
    ),
    version=API_VERSION,
    lifespan=lifespan,
)


# 配置跨域访问。
#
# 当前处于开发阶段，允许任意来源访问。
# allow_credentials=False可以与通配来源配合使用。
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

async def get_or_generate_background(
    force_refresh: bool = False,
) -> BackgroundDialogueResponse:
    """读取背景缓存，或者批量生成新的NPC背景状态。"""

    # 获取背景缓存管理器。
    background_cache = (
        application_context.background_cache
    )

    # 没有强制刷新时，优先读取有效缓存。
    if not force_refresh:
        cache_record = background_cache.load_valid()

        if cache_record is not None:
            # 将缓存内容同步到NPC状态管理器。
            application_context.state_manager.update_background_states(
                background_result=cache_record.result,
            )

            # 返回缓存中的背景状态。
            return BackgroundDialogueResponse(
                scene_summary=(
                    cache_record.result.scene_summary
                ),
                generated_at=cache_record.generated_at,
                dialogues=cache_record.result.dialogues,
            )

    # 使用异步锁防止并发重复生成。
    async with background_generation_lock:
        # 等待锁期间，其他请求可能已经生成了缓存。
        #
        # 非强制刷新请求需要再次检查缓存。
        if not force_refresh:
            cache_record = background_cache.load_valid()

            if cache_record is not None:
                application_context.state_manager.update_background_states(
                    background_result=cache_record.result,
                )

                return BackgroundDialogueResponse(
                    scene_summary=(
                        cache_record.result.scene_summary
                    ),
                    generated_at=cache_record.generated_at,
                    dialogues=(
                        cache_record.result.dialogues
                    ),
                )

        # 根据当前时间生成赛博小镇场景。
        scene_context = build_scene_context(
            weather="天气晴朗，微风轻柔",
            special_event=None,
        )

        try:
            # 获取全部NPC公开资料。
            npcs = (
                application_context
                .npc_manager
                .get_all_npcs()
            )

            # BatchDialogueGenerator是同步函数。
            #
            # 使用asyncio.to_thread放到工作线程执行，
            # 避免DeepSeek请求阻塞其他FastAPI接口。
            background_result = await asyncio.to_thread(
                application_context
                .batch_dialogue_generator
                .generate,
                npcs=npcs,
                scene_context=scene_context,
            )

            # 保存最新背景对话缓存。
            background_cache.save(
                scene_context=scene_context,
                result=background_result,
            )

            # 将新背景同步到NPC状态管理器。
            application_context.state_manager.update_background_states(
                background_result=background_result,
            )

            # 重新读取缓存，以取得准确生成时间。
            saved_record = background_cache.load()

            if saved_record is None:
                raise RuntimeError(
                    "背景对话已经生成，但缓存读取失败"
                )

            return BackgroundDialogueResponse(
                scene_summary=(
                    background_result.scene_summary
                ),
                generated_at=saved_record.generated_at,
                dialogues=background_result.dialogues,
            )

        except Exception as error:
            # 把背景生成错误写入日志。
            application_context.dialogue_logger.log_error(
                context="FastAPI批量生成NPC背景对话",
                error=error,
            )

            # 强制刷新失败时尝试返回原来的有效缓存。
            old_cache_record = (
                background_cache.load_valid()
            )

            if old_cache_record is not None:
                return BackgroundDialogueResponse(
                    scene_summary=(
                        old_cache_record
                        .result
                        .scene_summary
                    ),
                    generated_at=(
                        old_cache_record.generated_at
                    ),
                    dialogues=(
                        old_cache_record
                        .result
                        .dialogues
                    ),
                )

            # 没有可用缓存时返回503。
            raise HTTPException(
                status_code=503,
                detail=(
                    "NPC背景状态暂时无法生成，"
                    "请稍后再试"
                ),
            ) from error

@app.get(
    "/",
    response_model=HealthResponse,
    tags=["系统"],
)
async def root() -> HealthResponse:
    """返回后端服务基本运行状态。"""

    # 获取当前已经初始化的NPC数量。
    npc_count = (
        application_context
        .state_manager
        .get_npc_count()
    )

    # 返回经过Pydantic验证的健康状态。
    return HealthResponse(
        status="running",
        message="赛博小镇后端正在运行",
        version=API_VERSION,
        npc_count=npc_count,
    )


@app.get(
    "/health",
    response_model=HealthResponse,
    tags=["系统"],
)
async def health_check() -> HealthResponse:
    """返回后端详细健康检查结果。"""

    # 获取当前已经初始化的NPC数量。
    npc_count = (
        application_context
        .state_manager
        .get_npc_count()
    )

    # 返回组件初始化状态。
    return HealthResponse(
        status="running",
        message="全部核心组件已经初始化",
        version=API_VERSION,
        npc_count=npc_count,
    )


@app.get(
    "/npcs/status",
    response_model=NPCStatusListResponse,
    tags=["NPC状态"],
)
async def get_all_npc_status() -> NPCStatusListResponse:
    """返回全部NPC的当前运行状态。"""

    # 从状态管理器取得全部NPC状态副本。
    npc_states = (
        application_context
        .state_manager
        .get_all_npc_states()
    )

    # 返回全部NPC状态。
    return NPCStatusListResponse(
        npc_count=len(npc_states),
        npcs=npc_states,
    )

#@app.get 的作用就是将下面紧跟着的函数，注册为一个处理特定网络请求的“接口”
@app.get(
    "/npcs/{npc_id}/status",
    response_model=NPCState,
    tags=["NPC状态"],
)
async def get_single_npc_status(
    npc_id: str,
) -> NPCState:
    """根据npc_id返回单个NPC的运行状态。"""

    # 从状态管理器读取指定NPC。
    npc_state = (
        application_context
        .state_manager
        .get_npc_state(
            npc_id=npc_id,
        )
    )

    # NPC不存在时返回404。
    if npc_state is None:
        raise HTTPException(
            status_code=404,
            detail=f"NPC {npc_id} 不存在",
        )

    return npc_state


@app.get(
    "/affinity/{npc_id}/{player_id}",
    response_model=AffinityResponse,
    tags=["好感度"],
)
async def get_affinity(
    npc_id: str,
    player_id: str,
) -> AffinityResponse:
    """返回指定玩家与NPC之间的好感度。"""

    # 检查NPC是否存在。
    if not application_context.npc_manager.has_npc(
        npc_id=npc_id,
    ):
        raise HTTPException(
            status_code=404,
            detail=f"NPC {npc_id} 不存在",
        )

    # 玩家编号不能为空。
    cleaned_player_id = player_id.strip()

    if not cleaned_player_id:
        raise HTTPException(
            status_code=422,
            detail="player_id不能为空",
        )

    # 获取玩家与NPC之间的好感度记录。
    relationship = (
        application_context
        .relationship_manager
        .get_relationship(
            npc_id=npc_id,
            player_id=cleaned_player_id,
        )
    )

    # 转换成API响应模型。
    return AffinityResponse(
        npc_id=relationship.npc_id,
        player_id=relationship.player_id,
        affinity_score=relationship.score,
        affinity_level=relationship.level,
        interaction_count=(
            relationship.interaction_count
        ),
        last_change=relationship.last_change,
        last_reason=relationship.last_reason,
    )



@app.get(
    "/background",
    response_model=BackgroundDialogueResponse,
    tags=["背景对话"],
)
async def get_background_dialogues(
) -> BackgroundDialogueResponse:
    """返回有效背景缓存，过期时自动重新生成。"""

    # 默认优先使用有效缓存。
    return await get_or_generate_background(
        force_refresh=False,
    )


@app.post(
    "/background/refresh",
    response_model=BackgroundDialogueResponse,
    tags=["背景对话"],
)
async def refresh_background_dialogues(
) -> BackgroundDialogueResponse:
    """强制批量生成全部NPC的新背景状态。"""

    # 忽略现有缓存并调用一次DeepSeek。
    return await get_or_generate_background(
        force_refresh=True,
    )


@app.post(
    "/dialogue",
    response_model=DialogueResponse,
    tags=["NPC对话"],
)
async def create_dialogue(
    request: DialogueRequest,
) -> DialogueResponse:
    """处理玩家与指定NPC之间的一轮对话。"""

    try:
        # DialogueService内部包含多个同步操作，
        # 包括DeepSeek请求和Embedding计算。
        #
        # 使用asyncio.to_thread放入工作线程，
        # 避免阻塞FastAPI事件循环。
        dialogue_result = await asyncio.to_thread(
            dialogue_service.process_dialogue,
            npc_id=request.npc_id,
            player_id=request.player_id,
            player_message=request.player_message,
        )

        return dialogue_result

    except NPCNotFoundError as error:
        # NPC不存在时返回404。
        raise HTTPException(
            status_code=404,
            detail=str(error),
        ) from error

    except NPCBusyError as error:
        # NPC正在与其他玩家对话时返回409。
        raise HTTPException(
            status_code=409,
            detail=str(error),
        ) from error

    except Exception as error:
        # 详细错误已经由DialogueService写入日志。
        #
        # API只向前端返回通用说明，
        # 避免泄露服务器内部信息。
        raise HTTPException(
            status_code=500,
            detail="NPC对话处理失败，请稍后再试",
        ) from error



