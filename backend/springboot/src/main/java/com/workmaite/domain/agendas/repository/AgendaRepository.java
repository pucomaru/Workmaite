package com.workmaite.domain.agendas.repository;

import com.workmaite.domain.agendas.entity.Agenda;
import java.time.LocalDateTime;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface AgendaRepository extends JpaRepository<Agenda, Long> {

  List<Agenda> findByMeetingIdOrderByCreatedAt(Long meetingId);

  List<Agenda> findByAssigneeIdAndDueDateBetween(
      Long assigneeId, LocalDateTime start, LocalDateTime end);

  List<Agenda> findByMeetingIdInAndDueDateBetween(
      List<Long> meetingIds, LocalDateTime start, LocalDateTime end);

  // 세션 삭제 시 아젠다는 보존하되 세션 링크만 해제 (agenda.session_id FK, ON DELETE 없음)
  @Modifying
  @Query("UPDATE Agenda a SET a.sessionId = null WHERE a.sessionId = :sessionId")
  void detachSession(@Param("sessionId") Long sessionId);

  // 회의체 삭제 시: 아젠다 일괄 삭제 (session_agendas·report_agendas는 ON DELETE CASCADE).
  @Modifying
  @Query("DELETE FROM Agenda a WHERE a.meetingId = :meetingId")
  void deleteByMeetingId(@Param("meetingId") Long meetingId);
}
