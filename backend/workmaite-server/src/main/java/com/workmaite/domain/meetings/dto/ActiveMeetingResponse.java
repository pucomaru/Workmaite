package com.workmaite.domain.meetings.dto;

import com.workmaite.domain.meetings.entity.Meeting;
import com.workmaite.domain.meetings.entity.MeetingPriority;
import com.workmaite.domain.meetings.entity.MeetingType;
import lombok.Builder;
import lombok.Getter;

import java.time.LocalDateTime;

@Getter
@Builder
public class ActiveMeetingResponse {

    private Long meetingId;
    private String title;
    private MeetingPriority priority;
    private MeetingType type;
    private LocalDateTime endDate;
    private String secretaryName;

    public static ActiveMeetingResponse from(Meeting meeting, String secretaryName) {
        return ActiveMeetingResponse.builder()
                .meetingId(meeting.getId())
                .title(meeting.getTitle())
                .priority(meeting.getPriority())
                .type(meeting.getType())
                .endDate(meeting.getEndDate())
                .secretaryName(secretaryName)
                .build();
    }
}
