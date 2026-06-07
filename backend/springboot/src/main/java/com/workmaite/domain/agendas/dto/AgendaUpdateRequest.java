package com.workmaite.domain.agendas.dto;

import com.workmaite.domain.agendas.entity.AgendaStatus;
import lombok.Getter;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;

@Getter
@NoArgsConstructor
public class AgendaUpdateRequest {

    private String title;
    private AgendaStatus status;
    private String department;
    private LocalDateTime dueDate;
    private String priority;
}
