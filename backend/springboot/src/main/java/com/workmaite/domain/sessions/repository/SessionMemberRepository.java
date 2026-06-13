package com.workmaite.domain.sessions.repository;

import com.workmaite.domain.sessions.entity.SessionMember;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface SessionMemberRepository extends JpaRepository<SessionMember, Integer> {

  List<SessionMember> findBySessionId(Integer sessionId);

  void deleteBySessionId(Integer sessionId);
}
