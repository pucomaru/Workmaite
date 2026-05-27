package com.workmaite.domain.minutes.dto;

import jakarta.validation.constraints.NotBlank;
import lombok.Getter;
import lombok.NoArgsConstructor;

@Getter
@NoArgsConstructor
public class MinutesUpdateRequest {

    @NotBlank(message = "수정할 내용을 입력해주세요.")
    private String contentSummary;
}
