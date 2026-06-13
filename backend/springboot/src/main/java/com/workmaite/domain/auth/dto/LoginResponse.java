package com.workmaite.domain.auth.dto;

import com.workmaite.domain.user.dto.UserResponse;
import lombok.Builder;
import lombok.Getter;

@Getter
@Builder
public class LoginResponse {

  private String accessToken;
  private String refreshToken;
  private String tokenType;
  private UserResponse user;

  public static LoginResponse of(String accessToken, String refreshToken, UserResponse user) {
    return LoginResponse.builder()
        .accessToken(accessToken)
        .refreshToken(refreshToken)
        .tokenType("Bearer")
        .user(user)
        .build();
  }

  public static LoginResponse of(String accessToken, String refreshToken) {
    return LoginResponse.builder()
        .accessToken(accessToken)
        .refreshToken(refreshToken)
        .tokenType("Bearer")
        .build();
  }
}
