package com.workmaite.domain.chat.dto;

import com.workmaite.domain.chat.entity.ChatMessage;
import lombok.Builder;
import lombok.Getter;

import java.time.LocalDateTime;

@Getter
@Builder
public class ChatMessageResponse {
    private Long id;
    private String threadId;
    private String role;
    private String content;
    private Long meetingId;
    private LocalDateTime createdAt;

    public static ChatMessageResponse from(ChatMessage message) {
        return ChatMessageResponse.builder()
                .id(message.getId())
                .threadId(message.getThreadId())
                .role(message.getRole())
                .content(message.getContent())
                .meetingId(message.getMeetingId())
                .createdAt(message.getCreatedAt())
                .build();
    }
}
