package com.workmaite.domain.scripts.repository;

import com.workmaite.domain.scripts.entity.SttSegment;
import java.util.List;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;

public interface ScriptRepository extends JpaRepository<SttSegment, Integer> {

  // 세션에 속한 모든 세그먼트를 발화 시작 시간 오름차순으로 조회
  List<SttSegment> findBySessionIdOrderByStartSecAsc(Integer sessionId);

  // keyset 페이지네이션 (P8-3): afterSec 이후 세그먼트 limit개 (start_sec 오름차순)
  List<SttSegment> findBySessionIdAndStartSecGreaterThanOrderByStartSecAsc(
      Integer sessionId, Double afterSec, Pageable pageable);

  // 세션의 모든 세그먼트 삭제
  void deleteAllBySessionId(Integer sessionId);
}
