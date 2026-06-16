package com.workmaite.domain.logs.repository;

import com.workmaite.domain.logs.entity.AgentLog;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface AgentLogRepository extends JpaRepository<AgentLog, Long> {

  // 세션 삭제 시 에이전트 로그는 보존하고 세션 링크만 해제한다 (로그 이력 유지).
  // 행을 지우지 않으므로 token_usage_logs·hitl_reviews·chat_feedback(agent_logs.id 참조)도 그대로 보존된다.
  @Modifying
  @Query("UPDATE AgentLog a SET a.sessionId = null WHERE a.sessionId = :sessionId")
  void detachSession(@Param("sessionId") Long sessionId);
}
