package com.workmaite.domain.user.dto;

import jakarta.validation.constraints.NotBlank;
import lombok.Getter;
import lombok.NoArgsConstructor;

@Getter
@NoArgsConstructor
public class UpdateUserRequest {

    @NotBlank(message = "이름을 입력해주세요.")
    private String name;

    private String company;
    private String department;
    private String position;
}
