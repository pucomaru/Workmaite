package com.workmaite.domain.meetings.dto;

import com.fasterxml.jackson.annotation.JsonAlias;
import com.workmaite.domain.meetings.entity.MeetingType;
import jakarta.validation.constraints.NotBlank;
import lombok.Getter;
import lombok.NoArgsConstructor;

import java.time.LocalDate;
import java.time.LocalDateTime;

@Getter
@NoArgsConstructor
public class MeetingCreateRequest {

    @NotBlank(message = "회의체 제목을 입력해주세요.")
    private String title;

    private String description;
    private String guidelines;

    @JsonAlias({"meeting_type"})
    private MeetingType type;

    @JsonAlias({"start_date"})
    private LocalDate startDate;

    @JsonAlias({"end_date"})
    private LocalDate endDate;

    public LocalDateTime getStartDateTime() {
        return startDate != null ? startDate.atStartOfDay() : null;
    }

    public LocalDateTime getEndDateTime() {
        return endDate != null ? endDate.atStartOfDay() : null;
    }
}
