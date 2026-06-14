package com.workmaite.domain.scripts.entity;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.LocalDateTime;
import lombok.AccessLevel;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;
import org.hibernate.annotations.CreationTimestamp;

@Entity
@Table(name = "stt_segments")
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
@AllArgsConstructor
@Builder
public class SttSegment {

  @Id
  @GeneratedValue(strategy = GenerationType.IDENTITY)
  private Long id;

  @Column(name = "session_id", nullable = false)
  private Long sessionId;

  // 발화자 식별자 (예: SPEAKER_00, SPEAKER_01)
  @Column(name = "speaker_label", nullable = false, length = 50)
  private String speakerLabel;

  // 매핑된 시스템 사용자 ID (nullable - 미매핑 상태 허용)
  @Column(name = "speaker_user_id")
  private Long speakerUserId;

  @Column(nullable = false, columnDefinition = "TEXT")
  private String content;

  // 발화 시작 시간 (초 단위)
  @Column(name = "start_sec", nullable = false)
  private Double startSec;

  // 발화 종료 시간 (초 단위)
  @Column(name = "end_sec", nullable = false)
  private Double endSec;

  // STT 신뢰도 (0.0 ~ 1.0, nullable)
  @Column private Double confidence;

  @CreationTimestamp
  @Column(name = "created_at", updatable = false)
  private LocalDateTime createdAt;

  // 부분 수정: null이 아닌 필드만 업데이트
  public void update(
      String speakerLabel, Long speakerUserId, String content, Double startSec, Double endSec) {
    if (speakerLabel != null) this.speakerLabel = speakerLabel;
    if (speakerUserId != null) this.speakerUserId = speakerUserId;
    if (content != null) this.content = content;
    if (startSec != null) this.startSec = startSec;
    if (endSec != null) this.endSec = endSec;
  }
}
