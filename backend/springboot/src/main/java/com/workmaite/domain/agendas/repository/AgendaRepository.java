package com.workmaite.domain.agendas.repository;

import com.workmaite.domain.agendas.entity.Agenda;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface AgendaRepository extends JpaRepository<Agenda, Long> {

  List<Agenda> findByMeetingIdOrderByCreatedAt(Long meetingId);
}
