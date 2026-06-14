package com.workmaite.domain.minutes.entity;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
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

/** 회의록 엔티티 - minutes 테이블 매핑 */
@Entity
@Table(name = "minutes")
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
@AllArgsConstructor
@Builder
public class Minutes {

  @Id
  @GeneratedValue(strategy = GenerationType.IDENTITY)
  private Long id;

  @Column(name = "session_id", nullable = false, unique = true)
  private Long sessionId;

  @Column(name = "file_name", length = 255)
  private String fileName;

  @Column(name = "file_path", length = 500)
  private String filePath;

  @Column(name = "recorder_id")
  private Long recorderId;

  @Column(name = "content_original", columnDefinition = "TEXT")
  private String contentOriginal;

  @Column(name = "content_summary", columnDefinition = "TEXT")
  private String contentSummary;

  @Enumerated(EnumType.STRING)
  @Column(name = "status", length = 20, nullable = false)
  @Builder.Default
  private MinutesStatus status = MinutesStatus.DRAFT;

  @CreationTimestamp
  @Column(name = "generated_at", updatable = false)
  private LocalDateTime generatedAt;

  public void generate(String contentOriginal) {
    this.contentOriginal = contentOriginal;
  }

  public void updateSummary(String contentSummary) {
    this.contentSummary = contentSummary;
  }

  public void confirm(String contentSummary) {
    if (contentSummary != null) {
      this.contentSummary = contentSummary;
    }
    this.status = MinutesStatus.CONFIRMED;
  }
}
