package com.workmaite.domain.home.dto;

import com.workmaite.domain.sessions.entity.MeetingSession;
import com.workmaite.domain.sessions.entity.SessionStatus;
import lombok.Builder;
import lombok.Getter;

import java.time.LocalDateTime;

@Getter
@Builder
public class CalendarSessionItem {

    private Long sessionId;
    private String title;
    private String meetingTitle;
    private LocalDateTime scheduledAt;
    private String location;
    private SessionStatus status;

    public static CalendarSessionItem from(MeetingSession session, String meetingTitle) {
        return CalendarSessionItem.builder()
                .sessionId(session.getId())
                .title(session.getTitle())
                .meetingTitle(meetingTitle)
                .scheduledAt(session.getScheduledAt())
                .location(session.getLocation())
                .status(session.getStatus())
                .build();
    }
}
