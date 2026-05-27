package com.workmaite.domain.auth.dto;

import com.workmaite.domain.user.dto.UserResponse;
import lombok.Builder;
import lombok.Getter;

@Getter
@Builder
public class LoginResponse {

    private String accessToken;
    private String tokenType;
    private UserResponse user;

    public static LoginResponse of(String accessToken, UserResponse user) {
        return LoginResponse.builder()
                .accessToken(accessToken)
                .tokenType("Bearer")
                .user(user)
                .build();
    }

    public static LoginResponse of(String accessToken) {
        return LoginResponse.builder()
                .accessToken(accessToken)
                .tokenType("Bearer")
                .build();
    }
}
