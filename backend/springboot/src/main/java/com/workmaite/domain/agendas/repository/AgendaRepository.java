package com.workmaite.domain.agendas.repository;

import com.workmaite.domain.agendas.entity.Agenda;
import java.time.LocalDateTime;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface AgendaRepository extends JpaRepository<Agenda, Long> {

  List<Agenda> findByMeetingIdOrderByCreatedAt(Long meetingId);

  List<Agenda> findByAssigneeIdAndDueDateBetween(
      Long assigneeId, LocalDateTime start, LocalDateTime end);
}
