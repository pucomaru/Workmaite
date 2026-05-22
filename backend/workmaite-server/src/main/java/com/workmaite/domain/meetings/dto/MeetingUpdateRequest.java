package com.workmaite.domain.meetings.dto;

import com.workmaite.domain.meetings.entity.MeetingPriority;
import com.workmaite.domain.meetings.entity.MeetingStatus;
import com.workmaite.domain.meetings.entity.MeetingType;
import lombok.Getter;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;

@Getter
@NoArgsConstructor
public class MeetingUpdateRequest {

    private String title;
    private String purpose;
    private String guidelines;
    private MeetingPriority priority;
    private MeetingType type;
    private LocalDateTime startDate;
    private LocalDateTime endDate;
    private MeetingStatus status;
}
