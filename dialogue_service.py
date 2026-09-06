"""
NPC单轮对话业务服务模块。

功能说明：
具体怎么完成一轮对话统一交给 DialogueService。
负责处理一次完整的玩家与NPC对话，
包括NPC占用、长期记忆检索、回复生成、好感度更新、
对话档案保存、长期记忆提取、日志记录和NPC状态释放。

该模块不负责接收HTTP请求，
FastAPI接口只需要调用process_dialogue()即可。

主要变量含义：
- context：赛博小镇全部核心组件的统一容器。
- npc_id：玩家选择的NPC唯一编号。
- player_id：当前玩家唯一编号。
- player_message：玩家本轮发送的消息。
- npc：负责回复的NPC对象。
- interaction_started：玩家是否成功占用NPC。
- previous_state：NPC进入对话前的运行状态。
- memory_archive：当前NPC的完整原始对话档案。
- conversation_history：当前NPC最近几轮工作记忆。
- vector_memories：当前NPC的结构化长期记忆。
- query_plan：长期记忆查询规划结果。
- retrieved_memories：本轮检索到的长期记忆。
- relationship：玩家与NPC当前的好感度记录。
- previous_score：本轮更新前的好感度分数。
- relationship_update：本轮好感度更新结果。
- reply：NPC生成的回复。
- memory_statistics：本轮长期记忆写入统计。
- qdrant_store：由应用容器提供的Qdrant长期记忆存储器。
"""

from typing import TYPE_CHECKING

from api_models import DialogueResponse
from memory import (
    get_working_memory,
    load_memory,
    load_vector_memory,
    retrieve_relevant_memories,
    retrieve_relevant_memories_from_qdrant,
    save_memory,
)

# TYPE_CHECKING只在类型检查时导入，
# 可以避免运行期间出现循环导入。
if TYPE_CHECKING:
    from application_context import ApplicationContext


class NPCNotFoundError(ValueError):
    """请求的NPC不存在。"""


class NPCBusyError(RuntimeError):
    """请求的NPC当前正被其他玩家占用。"""


class DialogueService:
    """处理玩家与NPC单轮对话的业务服务。"""

    def __init__(
        self,
        context: "ApplicationContext",
    ) -> None:
        """保存赛博小镇应用组件容器。"""

        # 保存全部NPC、记忆、状态和日志组件。
        self.context = context

    def process_dialogue(
        self,
        npc_id: str,
        player_id: str,
        player_message: str,
    ) -> DialogueResponse:
        """处理一次完整的玩家与NPC对话。"""

        # 检查NPC是否存在。
        if not self.context.npc_manager.has_npc(
            npc_id=npc_id,
        ):
            raise NPCNotFoundError(
                f"NPC {npc_id} 不存在"
            )

        # 获取NPC对象。
        npc = self.context.npc_manager.get_npc(
            npc_id=npc_id,
        )

        # 防止NPC管理器状态异常。
        if npc is None:
            raise NPCNotFoundError(
                f"NPC {npc_id} 不存在"
            )

        # 保存NPC进入对话前的状态。
        previous_state = (
            self.context
            .state_manager
            .get_npc_state(
                npc_id=npc_id,
            )
        )

        # 原子化检查并占用NPC。
        interaction_started = (
            self.context
            .state_manager
            .try_begin_interaction(
                npc_id=npc_id,
                player_id=player_id,
            )
        )

        # NPC已经被占用时拒绝本次请求。
        if not interaction_started:
            raise NPCBusyError(
                f"NPC {npc_id} 正在与其他玩家交谈"
            )

        # 记录NPC进入对话状态。
        try:
            self.context.dialogue_logger.log_state_change(
                npc_id=npc_id,
                previous_status=(
                    previous_state.activity_status
                    if previous_state is not None
                    else "unknown"
                ),
                new_status="talking",
                player_id=player_id,
            )

        except Exception as log_error:
            # 状态日志失败不能中断对话。
            print(
                f"[NPC状态日志写入失败："
                f"{log_error}]"
            )

        try:
            # 加载当前NPC的完整原始对话档案。
            memory_archive = load_memory(
                npc_id=npc_id,
            )

            # 取得最近几轮工作记忆。
            conversation_history = get_working_memory(
                memory_archive=memory_archive,
            )


            # 获取更新前的好感度。
            relationship = (
                self.context
                .relationship_manager
                .get_relationship(
                    npc_id=npc_id,
                    player_id=player_id,
                )
            )

            previous_score = relationship.score

            # 默认没有查询计划。
            query_plan = None

            # 使用DeepSeek生成长期记忆查询计划。
            try:
                query_plan = (
                    self.context
                    .memory_query_planner
                    .plan(
                        user_message=player_message,
                    )
                )

            except Exception as error:
                # 查询规划失败时记录错误，
                # 后续退回纯Embedding检索。
                self._log_error_safely(
                    context="生成长期记忆查询计划",
                    error=error,
                    npc_id=npc_id,
                    player_id=player_id,
                )

            
            # ==================================================
            # 使用Qdrant检索长期记忆
            # ==================================================

            try:
                # 正常情况下只查询Qdrant，
                # 不读取旧版向量JSON。
                retrieved_memories = (
                    retrieve_relevant_memories_from_qdrant(
                        qdrant_store=(
                            self.context.qdrant_store
                        ),
                        npc_id=npc_id,
                        player_id=player_id,
                        query=player_message,
                        embedding_model=(
                            self.context
                            .embedding_model
                        ),
                        query_plan=query_plan,
                    )
                )

                print(
                    f"[Qdrant检索到"
                    f"{len(retrieved_memories)}条"
                    f"长期记忆]"
                )

            except Exception as qdrant_error:
                # Qdrant发生真实异常时，
                # 才读取旧版JSON进行回退。
                self._log_error_safely(
                    context="Qdrant长期记忆检索",
                    error=qdrant_error,
                    npc_id=npc_id,
                    player_id=player_id,
                )

                print(
                    "[Qdrant检索失败，"
                    "正在回退旧版JSON记忆]"
                )

                try:
                    # 只有Qdrant出现故障时，
                    # 才从磁盘读取完整向量JSON。
                    json_vector_memories = (
                        load_vector_memory(
                            npc_id=npc_id,
                        )
                    )

                    retrieved_memories = (
                        retrieve_relevant_memories(
                            vector_memories=(
                                json_vector_memories
                            ),
                            query=player_message,
                            embedding_model=(
                                self.context
                                .embedding_model
                            ),
                            query_plan=query_plan,
                        )
                    )

                    print(
                        f"[JSON回退检索到"
                        f"{len(retrieved_memories)}条"
                        f"长期记忆]"
                    )

                except Exception as json_error:
                    # Qdrant和JSON都失败时，
                    # 使用空长期记忆继续生成NPC回复。
                    retrieved_memories = []

                    self._log_error_safely(
                        context="JSON长期记忆回退检索",
                        error=json_error,
                        npc_id=npc_id,
                        player_id=player_id,
                    )

            
            # 使用记忆和当前好感度生成NPC回复。
            reply = npc.generate_reply(
                conversation_history=conversation_history,
                retrieved_memories=retrieved_memories,
                user_message=player_message,
                affinity_level=relationship.level,
                affinity_score=relationship.score,
            )

            # 默认没有好感度更新结果。
            relationship_update = None

            # 分析玩家态度并更新好感度。
            try:
                relationship_update = (
                    self.context
                    .relationship_manager
                    .update_relationship(
                        npc_id=npc_id,
                        player_id=player_id,
                        player_message=player_message,
                    )
                )

                # 保存更新后的关系记录。
                relationship = (
                    relationship_update.relationship
                )

            except Exception as error:
                # 好感度失败不影响正常对话结果。
                self._log_error_safely(
                    context="更新NPC好感度",
                    error=error,
                    npc_id=npc_id,
                    player_id=player_id,
                )

            # 将玩家消息加入完整档案。
            memory_archive.append(
                {
                    "role": "user",
                    "content": player_message,
                }
            )

            # 将NPC回复加入完整档案。
            memory_archive.append(
                {
                    "role": "assistant",
                    "content": reply,
                }
            )

            # 保存完整原始对话档案。
            try:
                save_memory(
                    npc_id=npc_id,
                    memory_archive=memory_archive,
                )

            except Exception as error:
                # 原始档案失败不影响API返回回复。
                self._log_error_safely(
                    context="保存NPC原始对话档案",
                    error=error,
                    npc_id=npc_id,
                    player_id=player_id,
                )

            # 从玩家原始消息中提取长期记忆。
            try:
                extraction_result = (
                    self.context
                    .memory_extractor
                    .extract(
                        user_message=player_message,
                    )
                )

                # 同时把记忆操作写入JSON和Qdrant。
                #
                # JSON目前仍然是主存储；
                # Qdrant同步失败不会导致整轮对话失败。
                # 使用QdrantMemoryManager执行长期记忆操作。
                #
                # 现在ADD、UPDATE和DELETE都以Qdrant为准，
                # 操作成功后再自动生成旧版JSON备份。
                memory_statistics = (
                    self.context
                    .qdrant_memory_manager
                    .apply_extraction(
                        npc_id=npc_id,
                        player_id=player_id,
                        extraction_result=(
                            extraction_result
                        ),
                    )
                )

                # 同时显示JSON操作和Qdrant同步情况，
                # 方便迁移阶段发现两种存储是否一致。
                print(
                    "[API长期记忆处理："
                    f"新增{memory_statistics['added']}条，"
                    f"更新{memory_statistics['updated']}条，"
                    f"删除{memory_statistics['deleted']}条，"
                    f"跳过{memory_statistics['skipped']}条；"
                    f"Qdrant写入"
                    f"{memory_statistics['qdrant_written']}条，"
                    f"Qdrant删除"
                    f"{memory_statistics['qdrant_deleted']}条，"
                    f"Qdrant失败"
                    f"{memory_statistics['qdrant_failed']}条，"
                    f"JSON备份失败"
                    f"{memory_statistics['backup_failed']}条]"
                )

            except Exception as error:
                # 长期记忆提取失败不影响对话结果。
                self._log_error_safely(
                    context="提取并保存NPC长期记忆",
                    error=error,
                    npc_id=npc_id,
                    player_id=player_id,
                )

            # 保存完整对话日志。
            try:
                self.context.dialogue_logger.log_dialogue(
                    npc_id=npc_id,
                    npc_name=npc.name,
                    player_id=player_id,
                    player_message=player_message,
                    npc_reply=reply,
                    retrieved_memories=(
                        retrieved_memories
                    ),
                    relationship_update=(
                        relationship_update
                    ),
                    previous_score=previous_score,
                )

            except Exception as log_error:
                # 日志失败不能影响API响应。
                print(
                    f"[对话日志写入失败："
                    f"{log_error}]"
                )

            # 好感度更新成功时返回实际变化值。
            if relationship_update is not None:
                affinity_change = (
                    relationship_update.applied_change
                )
            else:
                affinity_change = 0

            # 返回经过Pydantic验证的API响应。
            return DialogueResponse(
                npc_id=npc_id,
                npc_name=npc.name,
                npc_reply=reply,
                affinity_score=relationship.score,
                affinity_level=relationship.level,
                affinity_change=affinity_change,
                retrieved_memory_count=len(
                    retrieved_memories
                ),
            )

        except Exception as error:
            # 记录没有被局部处理的关键错误。
            self._log_error_safely(
                context="处理NPC单轮对话",
                error=error,
                npc_id=npc_id,
                player_id=player_id,
            )

            # 继续向上抛出，让FastAPI转换成500响应。
            raise

        finally:
            # 保存NPC释放前的状态。
            talking_state = (
                self.context
                .state_manager
                .get_npc_state(
                    npc_id=npc_id,
                )
            )

            # 无论成功还是失败都释放NPC。
            interaction_ended = (
                self.context
                .state_manager
                .end_interaction(
                    npc_id=npc_id,
                    player_id=player_id,
                )
            )

            # 读取NPC恢复后的状态。
            restored_state = (
                self.context
                .state_manager
                .get_npc_state(
                    npc_id=npc_id,
                )
            )

            # 释放成功后记录状态变化。
            if interaction_ended:
                try:
                    self.context.dialogue_logger.log_state_change(
                        npc_id=npc_id,
                        previous_status=(
                            talking_state.activity_status
                            if talking_state is not None
                            else "talking"
                        ),
                        new_status=(
                            restored_state.activity_status
                            if restored_state is not None
                            else "unknown"
                        ),
                        player_id=player_id,
                    )

                except Exception as log_error:
                    print(
                        f"[NPC状态日志写入失败："
                        f"{log_error}]"
                    )

    def _log_error_safely(
        self,
        context: str,
        error: Exception,
        npc_id: str,
        player_id: str,
    ) -> None:
        """记录错误，同时防止日志系统再次引发异常。"""

        try:
            # 将错误写入每日JSONL日志。
            self.context.dialogue_logger.log_error(
                context=context,
                error=error,
                npc_id=npc_id,
                player_id=player_id,
            )

        except Exception as log_error:
            # 日志系统自身失败时只在控制台显示。
            print(
                f"[错误日志写入失败："
                f"{log_error}]"
            )