package com.workmaite.domain.agendas.dto;

import com.workmaite.domain.agendas.entity.Agenda;
import com.workmaite.domain.agendas.entity.AgendaStatus;
import lombok.Builder;
import lombok.Getter;

import java.time.LocalDateTime;

@Getter
@Builder
public class AgendaResponse {

    private Long id;
    private Long meetingId;
    private Long sessionId;
    private String title;
    private AgendaStatus status;
    private Long assigneeId;
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
