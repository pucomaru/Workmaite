package com.workmaite.domain.organization.entity;

import jakarta.persistence.*;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.jpa.domain.support.AuditingEntityListener;

import java.time.LocalDateTime;

/**
 * 조직 구성원 엔티티 - organization_members 테이블 매핑
 */
@Entity
@Table(name = "organization_members")
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
@EntityListeners(AuditingEntityListener.class)
public class OrganizationMember {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "user_id", nullable = false, unique = true)
    private Long userId;

    @Column(name = "meeting_id")
    private Long meetingId;

    @Column(length = 100, nullable = false)
    private String name;

    @Column(length = 255, nullable = false)
    private String email;

    @Enumerated(EnumType.STRING)
    @Column(length = 20, nullable = false)
    private MemberRole role;

    @CreatedDate
    @Column(name = "created_at", nullable = false, updatable = false)
    private LocalDateTime createdAt;

    public static OrganizationMember create(Long userId, Long meetingId, String name, String email, MemberRole role) {
        OrganizationMember member = new OrganizationMember();
        member.userId = userId;
        member.meetingId = meetingId;
        member.name = name;
        member.email = email;
        member.role = role;
        return member;
    }

    public void update(MemberRole role) {
        if (role != null) this.role = role;
    }
}
