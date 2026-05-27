package com.workmaite.domain.sessions.entity;

import com.fasterxml.jackson.annotation.JsonProperty;

public enum SessionStatus {
    @JsonProperty("scheduled") SCHEDULED,
    @JsonProperty("ongoing") ONGOING,
    @JsonProperty("ended") ENDED
}
