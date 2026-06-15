package com.workmaite.domain.logs.entity;

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
@Table(name = "hitl_reviews")
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
@AllArgsConstructor
@Builder
public class HitlReview {

  @Id
  @GeneratedValue(strategy = GenerationType.IDENTITY)
  private Long id;

  @Column(name = "agent_log_id")
  private Long agentLogId;

  @Column(name = "target_type", length = 30, nullable = false)
  private String targetType;

  @Column(name = "ai_rationale", columnDefinition = "TEXT")
  private String aiRationale;

  @Builder.Default
  @Column(length = 20, nullable = false)
  private String status = "pending";

  @Column(name = "reviewer_id")
  private Long reviewerId;

  @Column(name = "reviewed_at")
  private LocalDateTime reviewedAt;

  @CreationTimestamp
  @Column(name = "created_at", updatable = false)
  private LocalDateTime createdAt;

  @Column(name = "agenda_id")
  private Long agendaId;

  @Column(name = "report_id")
  private Long reportId;

  @Column(name = "comment", columnDefinition = "TEXT")
  private String comment;

  public void review(String status, Long reviewerId, String comment) {
    this.status = status;
    this.reviewerId = reviewerId;
    this.comment = comment;
    this.reviewedAt = LocalDateTime.now();
  }
}
