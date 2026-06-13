package com.workmaite.domain.reports.entity;

import jakarta.persistence.*;
import java.time.LocalDateTime;
import lombok.*;
import org.hibernate.annotations.CreationTimestamp;

@Entity
@Table(name = "reports")
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
@AllArgsConstructor
@Builder
public class Report {

  @Id
  @GeneratedValue(strategy = GenerationType.IDENTITY)
  private Integer id;

  @Column(name = "meeting_id", nullable = false)
  private Integer meetingId;

  @Column(name = "parent_id")
  private Integer parentId;

  @Column(name = "upload_id", nullable = false)
  private Integer uploadId;

  @Builder.Default
  @Column(name = "version", nullable = false)
  private Integer version = 1;

  @Column(name = "submitter_department", length = 255, nullable = false)
  private String submitterDepartment;

  @Column(name = "file_name", length = 255)
  private String fileName;

  @Column(name = "file_path", length = 500)
  private String filePath;

  @Builder.Default
  @Column(name = "human_status", length = 20, nullable = false)
  private String humanStatus = "pending";

  @CreationTimestamp
  @Column(name = "created_at", updatable = false)
  private LocalDateTime createdAt;

  public void updateHumanStatus(String humanStatus) {
    this.humanStatus = humanStatus;
  }
}
