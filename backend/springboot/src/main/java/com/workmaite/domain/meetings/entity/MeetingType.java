package com.workmaite.domain.meetings.entity;

import com.fasterxml.jackson.annotation.JsonProperty;

public enum MeetingType {
    @JsonProperty("Weekly") WEEKLY,
    @JsonProperty("Monthly") MONTHLY,
    @JsonProperty("Quarterly") QUARTERLY
}
