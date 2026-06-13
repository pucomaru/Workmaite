package com.workmaite.domain.logs.entity;

import jakarta.persistence.*;
import java.time.LocalDateTime;
import lombok.*;
import org.hibernate.annotations.CreationTimestamp;

@Entity
@Table(name = "token_usage_logs")
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
@AllArgsConstructor
@Builder
public class TokenUsageLog {

  @Id
  @GeneratedValue(strategy = GenerationType.IDENTITY)
  private Integer id;

  @Column(name = "agent_log_id")
  private Integer agentLogId;

  @Column(name = "model_name", length = 50, nullable = false)
  private String modelName;

  @Column(name = "prompt_tokens", nullable = false)
  private Integer promptTokens;

  @Column(name = "completion_tokens", nullable = false)
  private Integer completionTokens;

  @Column(name = "cost")
  private Float cost;

  @CreationTimestamp
  @Column(name = "created_at", updatable = false)
  private LocalDateTime createdAt;
}
