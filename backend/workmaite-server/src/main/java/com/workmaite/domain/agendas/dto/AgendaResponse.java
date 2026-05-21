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
    private Long assigneeId;
    private String title;
    private String content;
    private Integer orderIndex;
    private AgendaStatus status;
    private LocalDateTime createdAt;

    public static AgendaResponse from(Agenda agenda) {
        return AgendaResponse.builder()
                .id(agenda.getId())
                .meetingId(agenda.getMeetingId())
                .assigneeId(agenda.getAssigneeId())
                .title(agenda.getTitle())
                .content(agenda.getContent())
                .orderIndex(agenda.getOrderIndex())
                .status(agenda.getStatus())
                .createdAt(agenda.getCreatedAt())
                .build();
    }
}
