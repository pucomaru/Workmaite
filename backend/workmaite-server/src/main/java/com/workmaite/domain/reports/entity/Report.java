package com.workmaite.domain.reports.entity;

import jakarta.persistence.*;
import lombok.*;
import org.hibernate.annotations.CreationTimestamp;

import java.time.LocalDateTime;

@Entity
@Table(name = "reports")
@Getter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class Report {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "meeting_id", nullable = false)
    private Long meetingId;

    @Column(name = "session_id")
    private Long sessionId;

    @Column(name = "uploader_id", nullable = false)
    private Long uploaderId;

    @Column(name = "parent_id")
    private Long parentId;

    @Builder.Default
    @Column(name = "version", nullable = false)
    private Integer version = 1;

    @Enumerated(EnumType.STRING)
    @Column(name = "file_type", length = 20, nullable = false)
    private ReportFileType fileType;

    @Column(name = "file_name", length = 255)
    private String fileName;

    @Column(name = "file_path", length = 500)
    private String filePath;

    @Enumerated(EnumType.STRING)
    @Builder.Default
    @Column(name = "status", length = 20, nullable = false)
    private ReportStatus status = ReportStatus.SUBMITTED;

    @Column(name = "score")
    private Float score;

    @Column(name = "layer1_result", columnDefinition = "jsonb")
    private String layer1Result;

    @Column(name = "layer2_result", columnDefinition = "jsonb")
    private String layer2Result;

    @Column(name = "layer3_result", columnDefinition = "jsonb")
    private String layer3Result;

    @Column(name = "feedback", columnDefinition = "TEXT")
    private String feedback;

    @Column(name = "missing_elements", columnDefinition = "jsonb")
    private String missingElements;

    @CreationTimestamp
    @Column(name = "created_at", updatable = false)
    private LocalDateTime createdAt;

    public void updateStatus(ReportStatus status) {
        this.status = status;
    }

    public void saveAnalysisResult(Float score, String layer1Result, String layer2Result,
                                   String layer3Result, String feedback, String missingElements) {
        this.score = score;
        this.layer1Result = layer1Result;
        this.layer2Result = layer2Result;
        this.layer3Result = layer3Result;
        this.feedback = feedback;
        this.missingElements = missingElements;
        this.status = ReportStatus.REVIEWING;
    }
}
