package com.workmaite.domain.meetings.dto;

import com.workmaite.domain.meetings.entity.MeetingPriority;
import com.workmaite.domain.meetings.entity.MeetingType;
import jakarta.validation.constraints.NotBlank;
import lombok.Getter;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;

@Getter
@NoArgsConstructor
public class MeetingCreateRequest {

    @NotBlank(message = "회의체 제목을 입력해주세요.")
    private String title;

    private String purpose;
    private String guidelines;
    private MeetingPriority priority;
    private MeetingType type;
    private LocalDateTime startDate;
    private LocalDateTime endDate;
}
