package com.workmaite.domain.agendas.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import lombok.Getter;
import lombok.NoArgsConstructor;

@Getter
@NoArgsConstructor
public class AgendaCreateRequest {

    @NotBlank(message = "안건 제목은 필수입니다.")
    private String title;

    private String content;

    @NotNull(message = "순서는 필수입니다.")
    private Integer orderIndex;
}
