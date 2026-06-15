package com.workmaite.domain.sessions.entity;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.LocalDateTime;
import java.util.List;
import lombok.Getter;
import lombok.NoArgsConstructor;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

@Entity
@Table(name = "session_summary_blocks")
@Getter
@NoArgsConstructor
public class SessionSummaryBlock {

  @Id
  @GeneratedValue(strategy = GenerationType.IDENTITY)
  private Long id;

  @Column(name = "session_id", nullable = false)
  private Long sessionId;

  @Column(name = "block_index", nullable = false)
  private Integer blockIndex;

  @Column(length = 500)
  private String title;

  @JdbcTypeCode(SqlTypes.JSON)
  @Column(columnDefinition = "jsonb")
  private List<String> bullets;

  @Column(name = "created_at")
  private LocalDateTime createdAt;

  @Column(name = "recording_start_sec")
  private Double recordingStartSec;

  @Column(name = "recording_end_sec")
  private Double recordingEndSec;
}
