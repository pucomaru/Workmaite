package com.workmaite.domain.meetings.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import com.workmaite.domain.meetings.entity.MeetingMember;
import com.workmaite.domain.meetings.entity.MeetingMemberRole;
import com.workmaite.domain.user.entity.User;
import lombok.Builder;
import lombok.Getter;

@Getter
@Builder
public class MeetingMemberResponse {

    private Long id;

    @JsonProperty("meeting_id")
    private Long meetingId;

    @JsonProperty("user_id")
    private Long userId;

    private MeetingMemberRole role;

    private String priority;

    private UserInfo user;

    @Getter
    @Builder
    public static class UserInfo {
        private Long id;
        private String name;
        private String email;
        private String company;
        private String department;
        private String position;
    }

    public static MeetingMemberResponse from(MeetingMember member) {
        return from(member, null);
    }

    public static MeetingMemberResponse from(MeetingMember member, User user) {
        UserInfo userInfo = user == null ? null : UserInfo.builder()
                .id(user.getId())
                .name(user.getName())
                .email(user.getEmail())
                .company(user.getCompany())
                .department(user.getDepartment())
                .position(user.getPosition())
                .build();
        return MeetingMemberResponse.builder()
                .id(member.getId())
                .meetingId(member.getMeetingId())
                .userId(member.getUserId())
                .role(member.getRole())
                .priority(member.getPriority())
                .user(userInfo)
                .build();
    }
}
