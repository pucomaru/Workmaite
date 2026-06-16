package com.workmaite.domain.home.dto;

import com.workmaite.domain.sessions.entity.MeetingSession;
import com.workmaite.domain.sessions.entity.SessionStatus;
import java.time.LocalDateTime;
import lombok.Builder;
import lombok.Getter;

@Getter
@Builder
public class CalendarSessionItem {

  private Long sessionId;
  private String title;
  private String meetingTitle;
  private LocalDateTime scheduledAt;
  private String location;
  private SessionStatus status;
  private String meetingStatus;
  private boolean hasMinutes;

  public static CalendarSessionItem from(
      MeetingSession session, String meetingTitle, String meetingStatus, boolean hasMinutes) {
    return CalendarSessionItem.builder()
        .sessionId(session.getId())
        .title(session.getTitle())
        .meetingTitle(meetingTitle)
        .scheduledAt(session.getScheduledAt())
        .location(session.getLocation())
        .status(session.getStatus())
        .meetingStatus(meetingStatus)
        .hasMinutes(hasMinutes)
        .build();
  }
}
