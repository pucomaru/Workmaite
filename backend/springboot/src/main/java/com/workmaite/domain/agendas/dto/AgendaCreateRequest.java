package com.workmaite.domain.agendas.dto;

import jakarta.validation.constraints.NotBlank;
import java.time.LocalDateTime;
import lombok.Getter;
import lombok.NoArgsConstructor;

@Getter
@NoArgsConstructor
public class AgendaCreateRequest {

  @NotBlank(message = "안건 제목은 필수입니다.")
  private String title;

  private Integer sessionId;
  private String department;
  private LocalDateTime dueDate;
  private String priority;
}
