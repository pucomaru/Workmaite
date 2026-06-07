package com.workmaite.domain.sessions.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import com.workmaite.domain.sessions.entity.MeetingSession;
import com.workmaite.domain.sessions.entity.SessionStatus;
import lombok.Builder;
import lombok.Getter;

import java.time.LocalDateTime;

@Getter
@Builder
public class SessionResponse {

    private Long id;

    @JsonProperty("meeting_id")
    private Long meetingId;

    private String title;
    private String location;
    private SessionStatus status;

    @JsonProperty("scheduled_at")
    private LocalDateTime scheduledAt;

    @JsonProperty("started_at")
    private LocalDateTime startedAt;

    @JsonProperty("ended_at")
    private LocalDateTime endedAt;

    public static SessionResponse from(MeetingSession session) {
        return SessionResponse.builder()
                .id(session.getId())
                .meetingId(session.getMeetingId())
                .title(session.getTitle())
                .location(session.getLocation())
                .status(session.getStatus())
                .scheduledAt(session.getScheduledAt())
                .startedAt(session.getStartedAt())
                .endedAt(session.getEndedAt())
                .build();
    }
}
