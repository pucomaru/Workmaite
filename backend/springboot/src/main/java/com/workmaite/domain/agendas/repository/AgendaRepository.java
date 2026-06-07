package com.workmaite.domain.agendas.repository;

import com.workmaite.domain.agendas.entity.Agenda;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

public interface AgendaRepository extends JpaRepository<Agenda, Long> {

    List<Agenda> findByMeetingIdOrderByCreatedAt(Long meetingId);
}
