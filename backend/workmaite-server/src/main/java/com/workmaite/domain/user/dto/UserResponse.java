package com.workmaite.domain.user.dto;

import com.workmaite.domain.user.entity.User;
import lombok.Builder;
import lombok.Getter;

import java.time.LocalDateTime;

@Getter
@Builder
public class UserResponse {

    private Long id;
    private String name;
    private String email;
    private String company;
    private String department;
    private String position;
    private LocalDateTime createdAt;

    public static UserResponse from(User user) {
        return UserResponse.builder()
                .id(user.getId())
                .name(user.getName())
                .email(user.getEmail())
                .company(user.getCompany())
                .department(user.getDepartment())
                .position(user.getPosition())
                .createdAt(user.getCreatedAt())
                .build();
    }
}
