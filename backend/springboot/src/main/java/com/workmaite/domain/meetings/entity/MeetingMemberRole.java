package com.workmaite.domain.meetings.entity;

import com.fasterxml.jackson.annotation.JsonProperty;

public enum MeetingMemberRole {
    @JsonProperty("admin")
    SECRETARY,

    @JsonProperty("presenter")
    MEMBER
}
