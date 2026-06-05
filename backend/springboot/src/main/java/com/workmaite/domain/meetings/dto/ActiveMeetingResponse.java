package com.workmaite.domain.meetings.dto;

import com.workmaite.domain.meetings.entity.Meeting;
import com.workmaite.domain.meetings.entity.MeetingType;
import lombok.Builder;
import lombok.Getter;

import java.time.LocalDateTime;

@Getter
@Builder
public class ActiveMeetingResponse {

    private Long meetingId;
    private String title;
    private MeetingType type;
    private LocalDateTime endDate;
    private String adminName;

    public static ActiveMeetingResponse from(Meeting meeting, String adminName) {
        return ActiveMeetingResponse.builder()
                .meetingId(meeting.getId())
                .title(meeting.getTitle())
                .type(meeting.getType())
                .endDate(meeting.getEndDate())
                .adminName(adminName)
                .build();
    }
}
