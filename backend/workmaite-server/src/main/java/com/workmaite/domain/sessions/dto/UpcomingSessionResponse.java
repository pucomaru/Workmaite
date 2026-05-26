package com.workmaite.domain.sessions.dto;

import com.workmaite.domain.sessions.entity.MeetingSession;
import lombok.Builder;
import lombok.Getter;

import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.temporal.ChronoUnit;

@Getter
@Builder
public class UpcomingSessionResponse {

    private Long sessionId;
    private Long meetingId;
    private String title;
    private String meetingTitle;
    private LocalDateTime scheduledAt;
    private String location;
    private long dDay;

    public static UpcomingSessionResponse from(MeetingSession session, String meetingTitle, LocalDate today) {
        long dDay = ChronoUnit.DAYS.between(today, session.getScheduledAt().toLocalDate());
        return UpcomingSessionResponse.builder()
                .sessionId(session.getId())
                .meetingId(session.getMeetingId())
                .title(session.getTitle())
                .meetingTitle(meetingTitle)
                .scheduledAt(session.getScheduledAt())
                .location(session.getLocation())
                .dDay(dDay)
                .build();
    }
}
