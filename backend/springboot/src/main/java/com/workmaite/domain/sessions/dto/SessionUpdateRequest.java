package com.workmaite.domain.sessions.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import java.time.LocalDateTime;
import java.util.List;
import lombok.Getter;
import lombok.NoArgsConstructor;

@Getter
@NoArgsConstructor
public class SessionUpdateRequest {

  private String title;
  private String description;
  private String location;
  private String type;
  private String context;

  @JsonProperty("scheduled_at")
  private LocalDateTime scheduledAt;

  private List<AttendeeRequest> attendees;

  @JsonProperty("agenda_ids")
  private List<Long> agendaIds;
}
