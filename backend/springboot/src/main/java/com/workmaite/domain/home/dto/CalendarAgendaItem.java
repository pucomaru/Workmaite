package com.workmaite.domain.home.dto;

import com.workmaite.domain.agendas.entity.Agenda;
import java.time.LocalDateTime;
import lombok.Builder;
import lombok.Getter;

@Getter
@Builder
public class CalendarAgendaItem {

  private Long agendaId;
  private String title;
  private String meetingTitle;
  private LocalDateTime dueDate;

  public static CalendarAgendaItem from(Agenda agenda, String meetingTitle) {
    return CalendarAgendaItem.builder()
        .agendaId(agenda.getId())
        .title(agenda.getTitle())
        .meetingTitle(meetingTitle)
        .dueDate(agenda.getDueDate())
        .build();
  }
}
