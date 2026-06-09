package com.workmaite.domain.sessions.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Getter;
import lombok.NoArgsConstructor;

@Getter
@NoArgsConstructor
public class AttendeeRequest {

    @JsonProperty("user_id")
    private Long userId;

    private String role;
}
