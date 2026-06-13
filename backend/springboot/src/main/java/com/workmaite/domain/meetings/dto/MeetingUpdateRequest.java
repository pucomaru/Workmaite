package com.workmaite.domain.meetings.dto;

import com.fasterxml.jackson.annotation.JsonAlias;
import com.workmaite.domain.meetings.entity.MeetingStatus;
import com.workmaite.domain.meetings.entity.MeetingType;
import java.time.LocalDate;
import java.time.LocalDateTime;
import lombok.Getter;
import lombok.NoArgsConstructor;

@Getter
@NoArgsConstructor
public class MeetingUpdateRequest {

  private String title;
  private String description;
  private String guidelines;

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
