package com.workmaite.domain.agendas.dto;

import com.workmaite.domain.agendas.entity.Agenda;
import com.workmaite.domain.agendas.entity.AgendaStatus;
import java.time.LocalDateTime;
import lombok.Builder;
import lombok.Getter;

@Getter
@Builder
public class AgendaResponse {

  private Integer id;
  private Integer meetingId;
  private Integer sessionId;
  private String title;
  private AgendaStatus status;
  private Integer assigneeId;
  private String department;
  private LocalDateTime dueDate;
  private String priority;
  private String aiEvidence;
  private LocalDateTime createdAt;

  public static AgendaResponse from(Agenda agenda) {
    return AgendaResponse.builder()
        .id(agenda.getId())
        .meetingId(agenda.getMeetingId())
        .sessionId(agenda.getSessionId())
        .title(agenda.getTitle())
        .status(agenda.getStatus())
        .assigneeId(agenda.getAssigneeId())
        .department(agenda.getDepartment())
        .dueDate(agenda.getDueDate())
        .priority(agenda.getPriority())
        .aiEvidence(agenda.getAiEvidence())
        .createdAt(agenda.getCreatedAt())
        .build();
  }
}
