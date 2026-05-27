package com.workmaite.domain.meetings.dto;

import com.fasterxml.jackson.annotation.JsonAlias;
import com.workmaite.domain.meetings.entity.MeetingPriority;
import com.workmaite.domain.meetings.entity.MeetingStatus;
import com.workmaite.domain.meetings.entity.MeetingType;
import lombok.Getter;
import lombok.NoArgsConstructor;

import java.time.LocalDate;
import java.time.LocalDateTime;

@Getter
@NoArgsConstructor
public class MeetingUpdateRequest {

    private String title;
    private String purpose;
    private String guidelines;
    private MeetingPriority priority;

    @JsonAlias({"meeting_type"})
    private MeetingType type;

    @JsonAlias({"start_date"})
    private LocalDate startDate;

    @JsonAlias({"end_date"})
    private LocalDate endDate;

    private MeetingStatus status;

    public LocalDateTime getStartDateTime() {
        return startDate != null ? startDate.atStartOfDay() : null;
    }

    public LocalDateTime getEndDateTime() {
        return endDate != null ? endDate.atStartOfDay() : null;
    }
}
