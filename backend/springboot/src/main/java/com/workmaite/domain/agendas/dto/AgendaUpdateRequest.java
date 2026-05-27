package com.workmaite.domain.agendas.dto;

import com.workmaite.domain.agendas.entity.AgendaStatus;
import lombok.Getter;
import lombok.NoArgsConstructor;

@Getter
@NoArgsConstructor
public class AgendaUpdateRequest {

    private String title;

    private String content;

    private Integer orderIndex;

    private AgendaStatus status;
}
