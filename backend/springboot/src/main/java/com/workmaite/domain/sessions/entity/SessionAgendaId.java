package com.workmaite.domain.sessions.entity;

import java.io.Serializable;
import lombok.AllArgsConstructor;
import lombok.EqualsAndHashCode;
import lombok.NoArgsConstructor;

@NoArgsConstructor
@AllArgsConstructor
@EqualsAndHashCode
public class SessionAgendaId implements Serializable {
  private Long sessionId;
  private Long agendaId;
}
