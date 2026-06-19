package com.workmaite.domain.meetings.entity;

import com.fasterxml.jackson.annotation.JsonProperty;

public enum MeetingStatus {
  @JsonProperty("active")
  ACTIVE,
  @JsonProperty("ended")
  ENDED
}
