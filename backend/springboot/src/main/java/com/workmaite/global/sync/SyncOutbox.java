package com.workmaite.global.sync;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.PrePersist;
import jakarta.persistence.Table;
import java.time.LocalDateTime;
import lombok.AccessLevel;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

/** Neo4j 동기화 아웃박스 행 (P2-4). 비즈니스 트랜잭션과 함께 커밋되어, 디스패처가 커밋 후 FastAPI로 전달한다. */
@Entity
@Table(name = "neo4j_sync_outbox")
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
@AllArgsConstructor
@Builder
public class SyncOutbox {

  public static final String STATUS_PENDING = "pending";
  public static final String STATUS_DONE = "done";
  public static final String STATUS_FAILED = "failed";

  public static final int MAX_RETRY = 10;

  @Id
  @GeneratedValue(strategy = GenerationType.IDENTITY)
  private Long id;

  @Column(name = "entity_type", nullable = false, length = 30)
  private String entityType;

  @Column(name = "entity_id", nullable = false)
  private Long entityId;

  @Column(nullable = false, length = 10)
  private String op;

  @JdbcTypeCode(SqlTypes.JSON)
  @Column(columnDefinition = "jsonb")
  private String payload;

  @Column(nullable = false, length = 15)
  @Builder.Default
  private String status = STATUS_PENDING;

  @Column(name = "retry_count", nullable = false)
  @Builder.Default
  private int retryCount = 0;

  @Column(name = "last_error")
  private String lastError;

  @Column(name = "created_at", nullable = false, updatable = false)
  private LocalDateTime createdAt;

  @Column(name = "processed_at")
  private LocalDateTime processedAt;

  @PrePersist
  protected void onCreate() {
    createdAt = LocalDateTime.now();
  }

  public void markDone() {
    this.status = STATUS_DONE;
    this.lastError = null;
    this.processedAt = LocalDateTime.now();
  }

  public void markAttemptFailed(String error) {
    this.retryCount++;
    this.lastError = error != null && error.length() > 500 ? error.substring(0, 500) : error;
    if (this.retryCount >= MAX_RETRY) {
      this.status = STATUS_FAILED;
    }
    this.processedAt = LocalDateTime.now();
  }
}
