package com.workmaite.domain.user.dto;

import com.workmaite.domain.user.entity.User;
import lombok.Builder;
import lombok.Getter;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;

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
    private List<Map<String, Object>> meetings;

    public static UserResponse from(User user) {
        return UserResponse.builder()
                .id(user.getId())
                .name(user.getName())
                .email(user.getEmail())
                .company(user.getCompany())
                .department(user.getDepartment())
                .position(user.getPosition())
                .createdAt(user.getCreatedAt())
                .meetings(List.of())
                .build();
    }

    public static UserResponse from(User user, List<Map<String, Object>> meetings) {
        return UserResponse.builder()
                .id(user.getId())
                .name(user.getName())
                .email(user.getEmail())
                .company(user.getCompany())
                .department(user.getDepartment())
                .position(user.getPosition())
                .createdAt(user.getCreatedAt())
                .meetings(meetings)
                .build();
    }
}
