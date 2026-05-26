package com.workmaite.domain.sessions.entity;

import jakarta.persistence.*;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.jpa.domain.support.AuditingEntityListener;

import java.time.LocalDateTime;

@Entity
@Table(name = "meeting_sessions")
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
@EntityListeners(AuditingEntityListener.class)
public class MeetingSession {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "meeting_id", nullable = false)
    private Long meetingId;

    @Column(length = 255)
    private String title;

    @Column(length = 255)
    private String location;

    @Column(name = "scheduled_at")
    private LocalDateTime scheduledAt;

    @Column(name = "started_at")
    private LocalDateTime startedAt;

    @Column(name = "ended_at")
    private LocalDateTime endedAt;

    @Enumerated(EnumType.STRING)
    @Column(length = 20, nullable = false)
    private SessionStatus status;

    @CreatedDate
    @Column(name = "created_at", nullable = false, updatable = false)
    private LocalDateTime createdAt;

    public static MeetingSession create(Long meetingId, String title, String location, LocalDateTime scheduledAt) {
        MeetingSession session = new MeetingSession();
        session.meetingId = meetingId;
        session.title = title;
        session.location = location;
        session.scheduledAt = scheduledAt;
        session.status = SessionStatus.SCHEDULED;
        return session;
    }

    public void update(String title, String location, LocalDateTime scheduledAt) {
        if (title != null) this.title = title;
        if (location != null) this.location = location;
        if (scheduledAt != null) this.scheduledAt = scheduledAt;
    }

    // SCHEDULED → ONGOING: 현재 시간을 started_at에 기록
    public void start() {
        this.startedAt = LocalDateTime.now();
        this.status = SessionStatus.ONGOING;
    }

    // ONGOING → SCHEDULED: 일시정지 시 started_at 초기화 후 대기 상태로 복귀
    public void pause() {
        this.startedAt = null;
        this.status = SessionStatus.SCHEDULED;
    }

    // ONGOING → ENDED: 현재 시간을 ended_at에 기록
    public void end() {
        this.endedAt = LocalDateTime.now();
        this.status = SessionStatus.ENDED;
    }
}
