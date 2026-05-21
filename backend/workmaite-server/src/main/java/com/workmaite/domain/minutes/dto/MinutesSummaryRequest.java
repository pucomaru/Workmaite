package com.workmaite.domain.minutes.dto;

import jakarta.validation.constraints.NotBlank;
import lombok.Getter;
import lombok.NoArgsConstructor;

@Getter
@NoArgsConstructor
public class MinutesSummaryRequest {

    @NotBlank(message = "STT 원문을 입력해주세요.")
    private String contentRaw;
}
