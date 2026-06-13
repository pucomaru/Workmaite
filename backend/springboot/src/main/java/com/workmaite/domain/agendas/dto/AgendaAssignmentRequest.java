package com.workmaite.domain.agendas.dto;

import jakarta.validation.constraints.NotNull;
import lombok.Getter;
import lombok.NoArgsConstructor;

@Getter
@NoArgsConstructor
public class AgendaAssignmentRequest {

  @NotNull(message = "담당자 ID는 필수입니다.")
  private Integer assigneeId;
}
