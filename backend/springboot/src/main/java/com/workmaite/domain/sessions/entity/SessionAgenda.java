package com.workmaite.domain.sessions.entity;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.IdClass;
import jakarta.persistence.Table;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;

@Entity
@Table(name = "session_agendas")
@IdClass(SessionAgendaId.class)
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class SessionAgenda {

  @Id
  @Column(name = "session_id", nullable = false)
  private Long sessionId;

  @Id
  @Column(name = "agenda_id", nullable = false)
  private Long agendaId;

  public static SessionAgenda of(Long sessionId, Long agendaId) {
    SessionAgenda sa = new SessionAgenda();
    sa.sessionId = sessionId;
    sa.agendaId = agendaId;
    return sa;
  }
}
