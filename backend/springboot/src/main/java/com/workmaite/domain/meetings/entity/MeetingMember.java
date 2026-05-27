package com.workmaite.domain.meetings.entity;

import jakarta.persistence.*;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.jpa.domain.support.AuditingEntityListener;

import java.time.LocalDateTime;

/**
 * 회의 참여자 엔티티 - meeting_members 테이블 매핑
 */
@Entity
@Table(
    name = "meeting_members",
    uniqueConstraints = @UniqueConstraint(columnNames = {"meeting_id", "user_id"})
)
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
@EntityListeners(AuditingEntityListener.class)
public class MeetingMember {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "meeting_id", nullable = false)
    private Long meetingId;

    @Column(name = "user_id", nullable = false)
    private Long userId;

    // SECRETARY | MEMBER
    @Enumerated(EnumType.STRING)
    @Column(length = 20, nullable = false)
    private MeetingMemberRole role;

    @CreatedDate
    @Column(name = "created_at", nullable = false, updatable = false)
    private LocalDateTime createdAt;

    public static MeetingMember create(Long meetingId, Long userId, MeetingMemberRole role) {
        MeetingMember member = new MeetingMember();
        member.meetingId = meetingId;
        member.userId = userId;
        member.role = (role != null) ? role : MeetingMemberRole.MEMBER;
        return member;
    }

    public void updateRole(MeetingMemberRole role) {
        this.role = role;
    }
}
