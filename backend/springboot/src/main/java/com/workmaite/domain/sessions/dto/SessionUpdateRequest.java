package com.workmaite.domain.sessions.dto;

import com.fasterxml.jackson.annotation.JsonAlias;
import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Getter;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;
import java.util.List;

@Getter
@NoArgsConstructor
public class SessionUpdateRequest {

    private String title;
    private String description;
    private String location;
    private String type;

    @JsonProperty("scheduled_at")
    private LocalDateTime scheduledAt;

    private List<AttendeeRequest> attendees;
}
