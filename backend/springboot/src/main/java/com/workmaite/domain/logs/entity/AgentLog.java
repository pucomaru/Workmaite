package com.workmaite.domain.logs.entity;

import jakarta.persistence.*;
import java.time.LocalDateTime;
import lombok.*;
import org.hibernate.annotations.CreationTimestamp;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

@Entity
@Table(name = "agent_logs")
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
@AllArgsConstructor
@Builder
public class AgentLog {

  @Id
  @GeneratedValue(strategy = GenerationType.IDENTITY)
  private Long id;

  @Column(name = "task_id", length = 100, nullable = false, unique = true)
  private String taskId;

  @Column(name = "context_type", length = 30, nullable = false)
  private String contextType;

  @Column(name = "meeting_id")
  private Long meetingId;

  @Column(name = "session_id")
  private Long sessionId;

  @Column(name = "user_id")
  private Long userId;

  @Builder.Default
  @Column(length = 20, nullable = false)
  private String status = "pending";

  @JdbcTypeCode(SqlTypes.JSON)
  @Column(name = "input_data", columnDefinition = "jsonb")
  private String inputData;

  @JdbcTypeCode(SqlTypes.JSON)
  @Column(name = "output_data", columnDefinition = "jsonb")
  private String outputData;

  @JdbcTypeCode(SqlTypes.JSON)
  @Column(name = "reasoning_steps", columnDefinition = "jsonb")
  private String reasoningSteps;

  @Builder.Default
  @Column(name = "loop_count")
  private Integer loopCount = 0;

  @Column(name = "error_message", columnDefinition = "TEXT")
  private String errorMessage;

  @Column(name = "ended_at")
  private LocalDateTime endedAt;

  @CreationTimestamp
  @Column(name = "created_at", updatable = false)
  private LocalDateTime createdAt;
}
