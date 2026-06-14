package com.workmaite.domain.user.entity;

import com.workmaite.domain.company.entity.Company;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.PrePersist;
import jakarta.persistence.PreUpdate;
import jakarta.persistence.Table;
import java.time.LocalDateTime;
import lombok.AccessLevel;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;

/** 사용자 엔티티 - users 테이블 매핑 */
@Entity
@Table(name = "users")
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
@AllArgsConstructor
@Builder
public class User {

  @Id
  @GeneratedValue(strategy = GenerationType.IDENTITY)
  private Long id;

  @Column(nullable = false, length = 100)
  private String name;

  @Column(nullable = false, unique = true, length = 255)
  private String email;

  // BCrypt 해시된 비밀번호
  @Column(name = "password_hash", nullable = false, length = 255)
  private String passwordHash;

  @Column(length = 100)
  private String department;

  @Column(length = 100)
  private String position;

  // 조직(회사) 수준 역할 (P1-3) — 회의체 권한(meeting_members.role=meetingRole)과 구분.
  // DB 컬럼명은 role 유지(매핑만 company_role 의미로 명명).
  @Enumerated(EnumType.STRING)
  @Column(name = "role", nullable = false, length = 30)
  @Builder.Default
  private UserRole companyRole = UserRole.USER;

  // 회사 정규화 (P1-7②, MT-4) — users.company 문자열을 대체
  @ManyToOne(fetch = FetchType.EAGER)
  @JoinColumn(name = "company_id")
  private Company company;

  @Column(name = "must_change_password", nullable = false)
  @Builder.Default
  private boolean mustChangePassword = false;

  @Column(name = "is_active", nullable = false)
  @Builder.Default
  private boolean isActive = true;

  @Column(name = "created_at", nullable = false, updatable = false)
  private LocalDateTime createdAt;

  @Column(name = "updated_at")
  private LocalDateTime updatedAt;

  @PrePersist
  protected void onCreate() {
    createdAt = LocalDateTime.now();
    updatedAt = LocalDateTime.now();
  }

  @PreUpdate
  protected void onUpdate() {
    updatedAt = LocalDateTime.now();
  }

  public void update(String name, String department, String position) {
    this.name = name;
    this.department = department;
    this.position = position;
  }

  public void updatePassword(String encodedPassword) {
    this.passwordHash = encodedPassword;
    this.mustChangePassword = false; // 변경 완료 — 강제 플래그 해제 (P1-7②)
  }

  public void changeCompanyRole(UserRole companyRole) {
    this.companyRole = companyRole;
  }

  public void assignCompany(Company company) {
    this.company = company;
  }

  /** 호환용 — company_id 직접 접근 (관계 매핑 전환, P1-7②) */
  public Long getCompanyId() {
    return company != null ? company.getId() : null;
  }
}
