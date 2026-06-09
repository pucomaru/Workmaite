package com.workmaite.domain.sessions.entity;

import jakarta.persistence.*;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;

/**
 * 회의 세션 엔티티 - meeting_sessions 테이블 매핑
 */
@Entity
@Table(name = "meeting_sessions")
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class MeetingSession {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "meeting_id", nullable = false)
    private Long meetingId;

    @Column(length = 255)
    private String title;

    @Column(length = 255)
    private String description;

    @Column(length = 255)
    private String location;

    @Column(length = 255, nullable = false)
    private String type;

    @Column(name = "scheduled_at")
    private LocalDateTime scheduledAt;

    @Column(name = "started_at")
    private LocalDateTime startedAt;

    @Column(name = "ended_at")
    private LocalDateTime endedAt;

    @Convert(converter = SessionStatusConverter.class)
    @Column(length = 20, nullable = false)
    private SessionStatus status;

    public static MeetingSession create(Long meetingId, String title, String description, String location, String type, LocalDateTime scheduledAt) {
        MeetingSession session = new MeetingSession();
        session.meetingId = meetingId;
        session.title = title;
        session.description = description;
        session.location = location;
        session.type = type;
        session.scheduledAt = scheduledAt;
        session.status = SessionStatus.SCHEDULED;
        return session;
    }

    public void update(String title, String description, String location, String type, LocalDateTime scheduledAt) {
        if (title != null) this.title = title;
        if (description != null) this.description = description;
        if (location != null) this.location = location;
        if (type != null) this.type = type;
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

    // ENDED → ARCHIVED: 회의록 아카이브 저장 완료
    public void archive() {
        this.status = SessionStatus.ARCHIVED;
    }
}
