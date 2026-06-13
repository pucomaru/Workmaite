package com.workmaite.domain.user.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import com.workmaite.domain.user.entity.User;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;
import lombok.Builder;
import lombok.Getter;

@Getter
@Builder
public class UserResponse {

  private Long id;
  private String name;
  private String email;
  private String company;
  private Long companyId;
  private String department;
  private String position;

  // 조직(회사) 권한 — 회의체 권한(meetingRole)과 구분. API 키는 기존대로 role 유지.
  @JsonProperty("role")
  private String companyRole;

  private boolean mustChangePassword; // 최초 로그인 시 비밀번호 변경 안내 (P1-7②)
  private LocalDateTime createdAt;
  private List<Map<String, Object>> meetings;

  public static UserResponse from(User user) {
    return from(user, List.of());
  }

  public static UserResponse from(User user, List<Map<String, Object>> meetings) {
    return UserResponse.builder()
        .id(user.getId())
        .name(user.getName())
        .email(user.getEmail())
        .company(user.getCompany() != null ? user.getCompany().getName() : null)
        .companyId(user.getCompanyId())
        .department(user.getDepartment())
        .position(user.getPosition())
        .companyRole(user.getCompanyRole() != null ? user.getCompanyRole().name() : null)
        .mustChangePassword(user.isMustChangePassword())
        .createdAt(user.getCreatedAt())
        .meetings(meetings)
        .build();
  }
}
