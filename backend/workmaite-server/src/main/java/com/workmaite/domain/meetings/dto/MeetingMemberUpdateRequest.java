package com.workmaite.domain.meetings.dto;

import com.workmaite.domain.meetings.entity.MeetingMemberRole;
import jakarta.validation.constraints.NotNull;
import lombok.Getter;
import lombok.NoArgsConstructor;

@Getter
@NoArgsConstructor
public class MeetingMemberUpdateRequest {

    @NotNull(message = "역할은 필수입니다.")
    private MeetingMemberRole role;
}
