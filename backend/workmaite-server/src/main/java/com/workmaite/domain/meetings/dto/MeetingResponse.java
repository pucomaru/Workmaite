package com.workmaite.domain.meetings.dto;

import com.workmaite.domain.meetings.entity.Meeting;
import com.workmaite.domain.meetings.entity.MeetingPriority;
import com.workmaite.domain.meetings.entity.MeetingStatus;
import com.workmaite.domain.meetings.entity.MeetingType;
import lombok.Builder;
import lombok.Getter;

import java.time.LocalDateTime;

@Getter
@Builder
public class MeetingResponse {

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

    public static MeetingResponse from(Meeting meeting) {
        return MeetingResponse.builder()
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
                .build();
    }
}
