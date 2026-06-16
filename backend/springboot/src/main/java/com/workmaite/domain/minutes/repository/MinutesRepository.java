package com.workmaite.domain.minutes.repository;

import com.workmaite.domain.minutes.entity.Minutes;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface MinutesRepository extends JpaRepository<Minutes, Long> {

  Optional<Minutes> findBySessionId(Long sessionId);

  boolean existsBySessionId(Long sessionId);

  // bulk @Modifying — 엔티티를 로딩하지 않고 바로 삭제한다.
  // (파생 deleteBySessionId는 SELECT로 엔티티를 hydrate하는데, DB의 status 값이 enum(DRAFT/completed)에
  @Modifying
  @Query("DELETE FROM Minutes m WHERE m.sessionId = :sessionId")
  void deleteBySessionId(@Param("sessionId") Long sessionId);
}
