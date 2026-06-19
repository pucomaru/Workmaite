package com.workmaite.domain.sessions.entity;

import jakarta.persistence.Column;
import jakarta.persistence.Convert;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.PrePersist;
import jakarta.persistence.Table;
import java.time.LocalDateTime;
import java.time.temporal.ChronoUnit;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;

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

  @Column(columnDefinition = "TEXT")
  private String context;

  @Column(name = "recording_seconds", nullable = false)
  private Long recordingSeconds = 0L;

  @Column(name = "last_resumed_at")
  private LocalDateTime lastResumedAt;

  @Column(name = "created_at", updatable = false)
  private LocalDateTime createdAt;

  @PrePersist
  protected void onCreate() {
    if (this.createdAt == null) this.createdAt = LocalDateTime.now(java.time.ZoneOffset.UTC);
  }

  public static MeetingSession create(
      Long meetingId,
      String title,
      String description,
      String location,
      String type,
      LocalDateTime scheduledAt) {
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

  public void update(
      String title, String description, String location, String type, LocalDateTime scheduledAt) {
    if (title != null) this.title = title;
    if (description != null) this.description = description;
    if (location != null) this.location = location;
    if (type != null) this.type = type;
    if (scheduledAt != null) this.scheduledAt = scheduledAt;
  }

  // SCHEDULED → ONGOING: 현재 시간을 started_at, last_resumed_at에 기록
  public void start() {
    this.startedAt = LocalDateTime.now();
    this.lastResumedAt = LocalDateTime.now();
    this.status = SessionStatus.ONGOING;
  }

  // 녹음 일시정지: 시간 누적, status는 ONGOING 유지
  public void pause() {
    if (this.lastResumedAt != null) {
      this.recordingSeconds += ChronoUnit.SECONDS.between(this.lastResumedAt, LocalDateTime.now());
    }
    this.lastResumedAt = null;
  }

  // 녹음 재개: last_resumed_at만 갱신
  public void resume() {
    this.lastResumedAt = LocalDateTime.now();
  }

  // ONGOING → ENDED: 마지막 녹음 구간 누적 후 종료
  public void end() {
    if (this.lastResumedAt != null) {
      this.recordingSeconds += ChronoUnit.SECONDS.between(this.lastResumedAt, LocalDateTime.now());
    }
    this.lastResumedAt = null;
    this.endedAt = LocalDateTime.now();
    this.status = SessionStatus.ENDED;
  }

  // ENDED → ARCHIVED: 회의록 아카이브 저장 완료
  public void archive() {
    this.status = SessionStatus.ARCHIVED;
  }

  public void updateContext(String context) {
    this.context = context;
  }
}
