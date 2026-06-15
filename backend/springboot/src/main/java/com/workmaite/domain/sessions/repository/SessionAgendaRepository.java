package com.workmaite.domain.sessions.repository;

import com.workmaite.domain.sessions.entity.SessionAgenda;
import com.workmaite.domain.sessions.entity.SessionAgendaId;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface SessionAgendaRepository extends JpaRepository<SessionAgenda, SessionAgendaId> {
  List<SessionAgenda> findBySessionId(Long sessionId);

  @Modifying
  @Query("DELETE FROM SessionAgenda a WHERE a.sessionId = :sessionId")
  void deleteBySessionId(@Param("sessionId") Long sessionId);
}
