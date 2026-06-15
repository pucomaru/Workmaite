package com.workmaite.domain.home.dto;

import java.util.List;
import lombok.Getter;

@Getter
public class CalendarResponse {

  private final List<CalendarSessionItem> sessions;
  private final List<CalendarAgendaItem> agendas;

  private CalendarResponse(List<CalendarSessionItem> sessions, List<CalendarAgendaItem> agendas) {
    this.sessions = sessions;
    this.agendas = agendas;
  }

  public static CalendarResponse of(
      List<CalendarSessionItem> sessions, List<CalendarAgendaItem> agendas) {
    return new CalendarResponse(sessions, agendas);
  }
}
