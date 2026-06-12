package com.workmaite.domain.scripts.repository;

import com.workmaite.domain.scripts.entity.SttSegment;
import org.springframework.data.jpa.repository.JpaRepository;

import org.springframework.data.domain.Pageable;

import java.util.List;

public interface ScriptRepository extends JpaRepository<SttSegment, Long> {

    // 세션에 속한 모든 세그먼트를 발화 시작 시간 오름차순으로 조회
    List<SttSegment> findBySessionIdOrderByStartSecAsc(Long sessionId);

    // keyset 페이지네이션 (P8-3): afterSec 이후 세그먼트 limit개 (start_sec 오름차순)
    List<SttSegment> findBySessionIdAndStartSecGreaterThanOrderByStartSecAsc(
            Long sessionId, Double afterSec, Pageable pageable);

    // 세션의 모든 세그먼트 삭제
    void deleteAllBySessionId(Long sessionId);
}
