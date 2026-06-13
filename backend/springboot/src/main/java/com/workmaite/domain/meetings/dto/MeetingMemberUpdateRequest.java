package com.workmaite.domain.meetings.dto;

import com.fasterxml.jackson.annotation.JsonAlias;
import com.fasterxml.jackson.annotation.JsonProperty;
import com.workmaite.domain.meetings.entity.MeetingMemberRole;
import jakarta.validation.constraints.NotNull;
import lombok.Getter;
import lombok.NoArgsConstructor;

@Getter
@NoArgsConstructor
public class MeetingMemberUpdateRequest {

  // 회의체 권한 (meeting_members.role). API 키는 기존대로 role.
  @JsonProperty("role")
  @JsonAlias({"meeting_role"})
  @NotNull(message = "역할은 필수입니다.")
  private MeetingMemberRole meetingRole;
}
