package com.workmaite.domain.minutes.repository;

import com.workmaite.domain.minutes.entity.Minutes;
import java.util.List;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface MinutesRepository extends JpaRepository<Minutes, Long> {

  Optional<Minutes> findBySessionId(Long sessionId);

  boolean existsBySessionId(Long sessionId);

  @Modifying
  @Query("DELETE FROM Minutes m WHERE m.sessionId = :sessionId")
  void deleteBySessionId(@Param("sessionId") Long sessionId);

  @Query("SELECT m.sessionId FROM Minutes m WHERE m.sessionId IN :sessionIds")
  List<Long> findSessionIdsBySessionIdIn(List<Long> sessionIds);
}
