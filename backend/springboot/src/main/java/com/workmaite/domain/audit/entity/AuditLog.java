package com.workmaite.domain.audit.entity;

import jakarta.persistence.*;
import lombok.AccessLevel;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

import java.time.LocalDateTime;

/**
 * 감사 로그 - audit_logs 테이블 매핑 (P1-6, BE-1).
 * "누가-언제-무엇을" 기록. 회사 시스템의 책임 추적 요건.
 */
@Entity
@Table(name = "audit_logs")
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
@AllArgsConstructor
@Builder
public class AuditLog {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "actor_id")
    private Long actorId;

    @Column(nullable = false, length = 40)
    private String action;        // CREATE/UPDATE/DELETE/APPROVE/LOGIN/...

    @Column(name = "entity_type", nullable = false, length = 40)
    private String entityType;    // meeting/report/agenda/minutes/member/...

    @Column(name = "entity_id")
    private Long entityId;

    @Column(name = "meeting_id")
    private Long meetingId;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(columnDefinition = "jsonb")
    private String detail;

    @Column(name = "ip_addr", length = 45)
    private String ipAddr;

    @Column(name = "created_at", nullable = false, updatable = false)
    private LocalDateTime createdAt;

    @PrePersist
    protected void onCreate() {
        createdAt = LocalDateTime.now();
    }
}
