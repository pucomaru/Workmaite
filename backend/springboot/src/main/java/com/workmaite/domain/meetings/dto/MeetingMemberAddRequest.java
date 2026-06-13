package com.workmaite.domain.meetings.dto;

import com.fasterxml.jackson.annotation.JsonAlias;
import com.fasterxml.jackson.annotation.JsonProperty;
import com.workmaite.domain.meetings.entity.MeetingMemberRole;
import jakarta.validation.constraints.NotNull;
import lombok.Getter;
import lombok.NoArgsConstructor;

@Getter
@NoArgsConstructor
public class MeetingMemberAddRequest {

  @JsonAlias({"user_id"})
  @NotNull(message = "userId는 필수입니다.")
  private Long userId;

  // 회의체 권한 (meeting_members.role) — null이면 MEMBER로 기본 설정. API 키는 기존대로 role.
  @JsonProperty("role")
  @JsonAlias({"meeting_role"})
  private MeetingMemberRole meetingRole;
}
