package com.workmaite.domain.logs.entity;

import jakarta.persistence.*;
import java.time.LocalDateTime;
import lombok.*;
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
  private Integer id;

  @Column(name = "agent_log_id")
  private Integer agentLogId;

  @Column(name = "target_type", length = 30, nullable = false)
  private String targetType;

  @Column(name = "target_id", nullable = false)
  private Integer targetId;

  @Column(name = "review_prompt", columnDefinition = "jsonb")
  private String reviewPrompt;

  @Column(name = "ai_rationale", columnDefinition = "TEXT")
  private String aiRationale;

  @Builder.Default
  @Column(length = 20, nullable = false)
  private String status = "pending";

  @Column(name = "reviewer_id")
  private Integer reviewerId;

  @Column(name = "review_comment", columnDefinition = "jsonb")
  private String reviewComment;

  @Column(name = "reviewed_at")
  private LocalDateTime reviewedAt;

  @CreationTimestamp
  @Column(name = "created_at", updatable = false)
  private LocalDateTime createdAt;

  public void review(String status, Integer reviewerId, String reviewComment) {
    this.status = status;
    this.reviewerId = reviewerId;
    this.reviewComment = reviewComment;
    this.reviewedAt = LocalDateTime.now();
  }
}
