package com.workmaite.domain.meetings.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import com.workmaite.domain.meetings.entity.Meeting;
import com.workmaite.domain.meetings.entity.MeetingType;
import java.time.LocalDateTime;
import lombok.Builder;
import lombok.Getter;

@Getter
@Builder
public class ActiveMeetingResponse {

  private Long meetingId;
  private String title;
  private MeetingType type;
  private LocalDateTime endDate;
  private String adminName;
  private int memberCount;

  // 현재 사용자의 회의체 권한(meeting_members.role). 멤버가 아닌 회의체는 null. API 키는 my_role.
  @JsonProperty("my_role")
  private String myRole;

  public static ActiveMeetingResponse from(
      Meeting meeting, String adminName, int memberCount, String myRole) {
    return ActiveMeetingResponse.builder()
        .meetingId(meeting.getId())
        .title(meeting.getTitle())
        .type(meeting.getType())
        .endDate(meeting.getEndDate())
        .adminName(adminName)
        .memberCount(memberCount)
        .myRole(myRole)
        .build();
  }
}
