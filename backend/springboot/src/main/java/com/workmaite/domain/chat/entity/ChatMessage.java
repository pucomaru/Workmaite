package com.workmaite.domain.chat.entity;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.LocalDateTime;
import lombok.AccessLevel;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;
import org.hibernate.annotations.CreationTimestamp;

@Entity
@Table(name = "chat_messages")
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
@AllArgsConstructor
@Builder
public class ChatMessage {

  @Id
  @GeneratedValue(strategy = GenerationType.IDENTITY)
  private Long id;

  @Column(name = "thread_id", length = 100, nullable = false)
  private String threadId;

  @Column(name = "user_id", nullable = false)
  private Long userId;

  @Column(length = 10, nullable = false)
  private String role;

  @Column(columnDefinition = "TEXT", nullable = false)
  private String content;

  @Column(name = "file_path", length = 500)
  private String filePath;

  @Column(name = "file_name", length = 255)
  private String fileName;

  @Column(name = "context_type", length = 20)
  private String contextType;

  @Column(name = "meeting_id")
  private Long meetingId;

  @Column(name = "session_id")
  private Long sessionId;

  @CreationTimestamp
  @Column(name = "created_at", updatable = false)
  private LocalDateTime createdAt;
}
