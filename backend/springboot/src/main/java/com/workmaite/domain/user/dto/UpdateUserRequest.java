package com.workmaite.domain.user.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
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

  @Pattern(regexp = "^(?=.*[A-Za-z])(?=.*\\d).{8,}$", message = "비밀번호는 8자 이상, 영문과 숫자를 포함해야 합니다.")
  private String password;
}
