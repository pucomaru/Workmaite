package com.workmaite.domain.meetings.dto;

import com.fasterxml.jackson.annotation.JsonAlias;
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

  private MeetingMemberRole role; // null이면 MEMBER로 기본 설정
}
