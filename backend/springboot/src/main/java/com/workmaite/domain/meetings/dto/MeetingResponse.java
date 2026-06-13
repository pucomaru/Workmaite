package com.workmaite.domain.meetings.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import com.workmaite.domain.meetings.entity.Meeting;
import com.workmaite.domain.meetings.entity.MeetingStatus;
import com.workmaite.domain.meetings.entity.MeetingType;
import java.time.LocalDateTime;
import lombok.Builder;
import lombok.Getter;

@Getter
@Builder
public class MeetingResponse {

  private Long id;
  private String title;
  private String description;
  private String guidelines;

  @JsonProperty("meeting_type")
  private MeetingType type;

  @JsonProperty("start_date")
  private LocalDateTime startDate;

  @JsonProperty("end_date")
  private LocalDateTime endDate;

  private MeetingStatus status;

  @JsonProperty("created_by")
  private Long createdBy;

  @JsonProperty("created_at")
  private LocalDateTime createdAt;

  @JsonProperty("my_role")
  private String myRole;

  public static MeetingResponse from(Meeting meeting) {
    return from(meeting, null);
  }

  public static MeetingResponse from(Meeting meeting, String myRole) {
    return MeetingResponse.builder()
        .id(meeting.getId())
        .title(meeting.getTitle())
        .description(meeting.getDescription())
        .guidelines(meeting.getGuidelines())
        .type(meeting.getType())
        .startDate(meeting.getStartDate())
        .endDate(meeting.getEndDate())
        .status(meeting.getStatus())
        .createdBy(meeting.getCreatedBy())
        .createdAt(meeting.getCreatedAt())
        .myRole(myRole)
        .build();
  }
}
