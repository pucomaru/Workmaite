package com.workmaite.domain.sessions.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import com.workmaite.domain.sessions.entity.MeetingSession;
import com.workmaite.domain.sessions.entity.SessionMember;
import com.workmaite.domain.sessions.entity.SessionStatus;
import lombok.Builder;
import lombok.Getter;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;

@Getter
@Builder
public class SessionResponse {

    private Long id;

    @JsonProperty("meeting_id")
    private Long meetingId;

    private String title;
    private String location;
    private String context;
    private SessionStatus status;

    @JsonProperty("scheduled_at")
    private LocalDateTime scheduledAt;

    @JsonProperty("started_at")
    private LocalDateTime startedAt;

    @JsonProperty("ended_at")
    private LocalDateTime endedAt;

    @JsonProperty("attendee_ids")
    private List<Long> attendeeIds;

    private List<Map<String, Object>> attendees;

    @JsonProperty("summary_blocks")
    private List<SummaryBlockResponse> summaryBlocks;

    public static SessionResponse from(MeetingSession session) {
        return SessionResponse.builder()
                .id(session.getId())
                .meetingId(session.getMeetingId())
                .title(session.getTitle())
                .location(session.getLocation())
                .context(session.getContext())
                .status(session.getStatus())
                .scheduledAt(session.getScheduledAt())
                .startedAt(session.getStartedAt())
                .endedAt(session.getEndedAt())
                .attendeeIds(List.of())
                .attendees(List.of())
                .build();
    }

    public static SessionResponse from(MeetingSession session, List<SessionMember> members) {
        return from(session, members, List.of());
    }

    public static SessionResponse from(MeetingSession session, List<SessionMember> members, List<SummaryBlockResponse> blocks) {
        List<Long> ids = members.stream().map(SessionMember::getUserId).toList();
        List<Map<String, Object>> attendees = members.stream()
                .map(m -> Map.<String, Object>of("userId", m.getUserId(), "role", m.getRole() != null ? m.getRole() : "member"))
                .toList();
        return SessionResponse.builder()
                .id(session.getId())
                .meetingId(session.getMeetingId())
                .title(session.getTitle())
                .location(session.getLocation())
                .context(session.getContext())
                .status(session.getStatus())
                .scheduledAt(session.getScheduledAt())
                .startedAt(session.getStartedAt())
                .endedAt(session.getEndedAt())
                .attendeeIds(ids)
                .attendees(attendees)
                .summaryBlocks(blocks)
                .build();
    }
}
