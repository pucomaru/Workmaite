package com.workmaite.domain.organization.dto;

import com.workmaite.domain.organization.entity.MemberRole;
import com.workmaite.domain.organization.entity.OrganizationMember;
import lombok.Builder;
import lombok.Getter;

import java.time.LocalDateTime;

@Getter
@Builder
public class OrganizationMemberResponse {

    private Long id;
    private Long userId;
    private Long meetingId;
    private String name;
    private String email;
    private MemberRole role;
    private LocalDateTime createdAt;

    public static OrganizationMemberResponse from(OrganizationMember member) {
        return OrganizationMemberResponse.builder()
                .id(member.getId())
                .userId(member.getUserId())
                .meetingId(member.getMeetingId())
                .name(member.getName())
                .email(member.getEmail())
                .role(member.getRole())
                .createdAt(member.getCreatedAt())
                .build();
    }
}
