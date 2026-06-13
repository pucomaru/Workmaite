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

  // 현재 사용자의 회의체 권한 (meeting_members.role 투영). API 키는 기존대로 my_role 유지.
  @JsonProperty("my_role")
  private String myMeetingRole;

  public static MeetingResponse from(Meeting meeting) {
    return from(meeting, null);
  }

  public static MeetingResponse from(Meeting meeting, String myMeetingRole) {
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
        .myMeetingRole(myMeetingRole)
        .build();
  }
}
