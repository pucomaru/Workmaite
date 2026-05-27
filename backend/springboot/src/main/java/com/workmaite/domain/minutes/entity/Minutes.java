package com.workmaite.domain.minutes.entity;

import jakarta.persistence.*;
import lombok.*;
import org.hibernate.annotations.CreationTimestamp;
import org.hibernate.annotations.UpdateTimestamp;

import java.time.LocalDateTime;

/**
 * 회의록 엔티티 - minutes 테이블 매핑
 */
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

    @Column(name = "recorder_id")
    private Long recorderId;

    @Column(name = "content_raw", columnDefinition = "TEXT")
    private String contentRaw;

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

    @UpdateTimestamp
    @Column(name = "updated_at")
    private LocalDateTime updatedAt;

    public void generate(String contentRaw, String contentOriginal) {
        this.contentRaw = contentRaw;
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