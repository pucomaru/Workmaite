package com.workmaite.domain.reports.entity;

import jakarta.persistence.*;
import java.time.LocalDateTime;
import lombok.*;
import org.hibernate.annotations.CreationTimestamp;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

@Entity
@Table(name = "report_scores")
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
@AllArgsConstructor
@Builder
public class ReportScore {

  @Id
  @GeneratedValue(strategy = GenerationType.IDENTITY)
  private Long id;

  @Column(name = "report_id", nullable = false)
  private Long reportId;

  @Builder.Default
  @Column(name = "ai_status", length = 20, nullable = false)
  private String aiStatus = "pending";

  @Column(name = "total_score")
  private Double totalScore;

  @JdbcTypeCode(SqlTypes.JSON)
  @Column(name = "detail_scores", columnDefinition = "jsonb")
  private String detailScores;

  @Column(name = "feedback", columnDefinition = "TEXT")
  private String feedback;

  @CreationTimestamp
  @Column(name = "created_at", updatable = false)
  private LocalDateTime createdAt;

  public void saveResult(String aiStatus, Double totalScore, String detailScores, String feedback) {
    this.aiStatus = aiStatus;
    this.totalScore = totalScore;
    this.detailScores = detailScores;
    this.feedback = feedback;
  }
}
