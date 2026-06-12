package com.workmaite.domain.sessions.repository;

import com.workmaite.domain.sessions.entity.SessionSummaryBlock;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

public interface SessionSummaryBlockRepository extends JpaRepository<SessionSummaryBlock, Long> {
    List<SessionSummaryBlock> findBySessionIdOrderByBlockIndexAsc(Long sessionId);
    void deleteAllBySessionId(Long sessionId);
}
