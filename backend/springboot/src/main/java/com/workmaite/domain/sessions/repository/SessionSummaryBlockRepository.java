package com.workmaite.domain.sessions.repository;

import com.workmaite.domain.sessions.entity.SessionSummaryBlock;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface SessionSummaryBlockRepository extends JpaRepository<SessionSummaryBlock, Long> {
  List<SessionSummaryBlock> findBySessionIdOrderByBlockIndexAsc(Long sessionId);

  void deleteAllBySessionId(Long sessionId);
}
