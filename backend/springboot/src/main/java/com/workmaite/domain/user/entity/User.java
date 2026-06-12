package com.workmaite.domain.user.entity;

import jakarta.persistence.*;
import lombok.*;

import java.time.LocalDateTime;

/**
 * 사용자 엔티티 - users 테이블 매핑
 */
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
    private String company;

    @Column(length = 100)
    private String department;

    @Column(length = 100)
    private String position;

    // 시스템 수준 역할 (P1-3) — position 문자열로 권한을 판별하던 것을 대체
    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 30)
    @Builder.Default
    private UserRole role = UserRole.USER;

    // 회사 정규화 FK (P1-7②, MT-4) — company 문자열은 과도기 유지
    @Column(name = "company_id")
    private Long companyId;

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

    public void update(String name, String company, String department, String position) {
        this.name = name;
        this.company = company;
        this.department = department;
        this.position = position;
    }

    public void updatePassword(String encodedPassword) {
        this.passwordHash = encodedPassword;
        this.mustChangePassword = false; // 변경 완료 — 강제 플래그 해제 (P1-7②)
    }

    public void changeRole(UserRole role) {
        this.role = role;
    }

    public void assignCompany(Long companyId) {
        this.companyId = companyId;
    }
}
