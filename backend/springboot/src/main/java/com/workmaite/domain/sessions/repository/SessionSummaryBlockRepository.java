package com.workmaite.domain.sessions.repository;

import com.workmaite.domain.sessions.entity.SessionSummaryBlock;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface SessionSummaryBlockRepository extends JpaRepository<SessionSummaryBlock, Integer> {
  List<SessionSummaryBlock> findBySessionIdOrderByBlockIndexAsc(Integer sessionId);

  void deleteAllBySessionId(Integer sessionId);
}
