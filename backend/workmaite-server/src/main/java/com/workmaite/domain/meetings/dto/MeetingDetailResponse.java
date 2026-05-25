package com.workmaite.domain.meetings.dto;

import com.workmaite.domain.meetings.entity.Meeting;
import com.workmaite.domain.meetings.entity.MeetingMember;
import com.workmaite.domain.meetings.entity.MeetingPriority;
import com.workmaite.domain.meetings.entity.MeetingStatus;
import com.workmaite.domain.meetings.entity.MeetingType;
import lombok.Builder;
import lombok.Getter;

import java.time.LocalDateTime;
import java.util.List;

@Getter
@Builder
public class MeetingDetailResponse {

    private Long id;
    private String title;
    private String purpose;
    private String guidelines;
    private MeetingPriority priority;
    private MeetingType type;
    private LocalDateTime startDate;
    private LocalDateTime endDate;
    private MeetingStatus status;
    private Long createdBy;
    private LocalDateTime createdAt;
    private List<MeetingMemberResponse> members;

    public static MeetingDetailResponse from(Meeting meeting, List<MeetingMember> members) {
        return MeetingDetailResponse.builder()
                .id(meeting.getId())
                .title(meeting.getTitle())
                .purpose(meeting.getPurpose())
                .guidelines(meeting.getGuidelines())
                .priority(meeting.getPriority())
                .type(meeting.getType())
                .startDate(meeting.getStartDate())
                .endDate(meeting.getEndDate())
                .status(meeting.getStatus())
                .createdBy(meeting.getCreatedBy())
                .createdAt(meeting.getCreatedAt())
                .members(members.stream().map(MeetingMemberResponse::from).toList())
                .build();
    }
}
