package com.workmaite.domain.scripts.repository;

import com.workmaite.domain.scripts.entity.SttSegment;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

public interface ScriptRepository extends JpaRepository<SttSegment, Long> {

    // 세션에 속한 모든 세그먼트를 발화 시작 시간 오름차순으로 조회
    List<SttSegment> findBySessionIdOrderByStartSecAsc(Long sessionId);

    // 세션의 모든 세그먼트 삭제
    void deleteAllBySessionId(Long sessionId);
}
