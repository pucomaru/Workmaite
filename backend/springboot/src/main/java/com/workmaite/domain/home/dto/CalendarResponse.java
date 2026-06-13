package com.workmaite.domain.home.dto;

import java.util.List;
import lombok.Getter;

@Getter
public class CalendarResponse {

  private final List<CalendarSessionItem> sessions;

  private CalendarResponse(List<CalendarSessionItem> sessions) {
    this.sessions = sessions;
  }

  public static CalendarResponse of(List<CalendarSessionItem> sessions) {
    return new CalendarResponse(sessions);
  }
}
