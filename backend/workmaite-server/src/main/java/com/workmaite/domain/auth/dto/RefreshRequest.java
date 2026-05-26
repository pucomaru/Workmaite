package com.workmaite.domain.auth.dto;

import jakarta.validation.constraints.NotBlank;
import lombok.Getter;
import lombok.NoArgsConstructor;

@Getter
@NoArgsConstructor
public class RefreshRequest {

    @NotBlank(message = "Refresh Token을 입력해주세요.")
    private String refreshToken;
}
