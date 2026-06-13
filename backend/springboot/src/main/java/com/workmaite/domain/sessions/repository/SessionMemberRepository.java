package com.workmaite.domain.sessions.repository;

import com.workmaite.domain.sessions.entity.SessionMember;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface SessionMemberRepository extends JpaRepository<SessionMember, Long> {

  List<SessionMember> findBySessionId(Long sessionId);

  void deleteBySessionId(Long sessionId);
}
