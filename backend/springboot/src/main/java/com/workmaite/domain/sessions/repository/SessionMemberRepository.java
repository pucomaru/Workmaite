package com.workmaite.domain.sessions.repository;

import com.workmaite.domain.sessions.entity.SessionMember;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface SessionMemberRepository extends JpaRepository<SessionMember, Long> {

  List<SessionMember> findBySessionId(Long sessionId);

  @Modifying
  @Query("DELETE FROM SessionMember m WHERE m.sessionId = :sessionId")
  void deleteBySessionId(@Param("sessionId") Long sessionId);
}
