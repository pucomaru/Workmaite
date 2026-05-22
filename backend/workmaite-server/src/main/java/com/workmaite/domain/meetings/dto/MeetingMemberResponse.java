package com.workmaite.domain.meetings.dto;

import com.workmaite.domain.meetings.entity.MeetingMember;
import com.workmaite.domain.meetings.entity.MeetingMemberRole;
import lombok.Builder;
import lombok.Getter;

import java.time.LocalDateTime;

@Getter
@Builder
public class MeetingMemberResponse {

    private Long id;
    private Long meetingId;
    private Long userId;
    private MeetingMemberRole role;
    private LocalDateTime createdAt;

    public static MeetingMemberResponse from(MeetingMember member) {
        return MeetingMemberResponse.builder()
                .id(member.getId())
                .meetingId(member.getMeetingId())
                .userId(member.getUserId())
                .role(member.getRole())
                .createdAt(member.getCreatedAt())
                .build();
    }
}
