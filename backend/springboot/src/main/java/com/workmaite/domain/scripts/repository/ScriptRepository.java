package com.workmaite.domain.scripts.repository;

import com.workmaite.domain.scripts.entity.SttSegment;
import java.util.List;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;

public interface ScriptRepository extends JpaRepository<SttSegment, Long> {

  List<SttSegment> findBySessionIdOrderByStartSecAsc(Long sessionId);

  // keyset 페이지네이션 (P8-3): afterSec 이후 세그먼트 limit개 (start_sec 오름차순)
  List<SttSegment> findBySessionIdAndStartSecGreaterThanOrderByStartSecAsc(
      Long sessionId, Double afterSec, Pageable pageable);

  void deleteAllBySessionId(Long sessionId);
}
