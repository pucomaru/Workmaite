package com.workmaite.domain.agendas.dto;

import jakarta.validation.constraints.NotBlank;
import lombok.Getter;
import lombok.NoArgsConstructor;

@Getter
@NoArgsConstructor
public class AgendaExtractRequest {

  @NotBlank(message = "추출할 내용은 필수입니다.")
  private String content;
}
