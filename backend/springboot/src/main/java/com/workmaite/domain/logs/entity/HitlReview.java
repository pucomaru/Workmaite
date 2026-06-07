package com.workmaite.domain.logs.entity;

import jakarta.persistence.*;
import lombok.*;
import org.hibernate.annotations.CreationTimestamp;

import java.time.LocalDateTime;

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

    @Column(name = "target_id", nullable = false)
    private Long targetId;

    @Column(name = "review_prompt", columnDefinition = "TEXT")
    private String reviewPrompt;

    @Column(name = "ai_rationale", columnDefinition = "TEXT")
    private String aiRationale;

    @Builder.Default
    @Column(length = 20, nullable = false)
    private String status = "pending";

    @Column(name = "reviewer_id")
    private Long reviewerId;

    @Column(name = "review_comment", columnDefinition = "TEXT")
    private String reviewComment;

    @Column(name = "reviewed_at")
    private LocalDateTime reviewedAt;

    @CreationTimestamp
    @Column(name = "created_at", updatable = false)
    private LocalDateTime createdAt;

    public void review(String status, Long reviewerId, String reviewComment) {
        this.status = status;
        this.reviewerId = reviewerId;
        this.reviewComment = reviewComment;
        this.reviewedAt = LocalDateTime.now();
    }
}
