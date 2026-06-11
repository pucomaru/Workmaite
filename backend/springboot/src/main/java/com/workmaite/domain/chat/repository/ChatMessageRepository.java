package com.workmaite.domain.chat.repository;

import com.workmaite.domain.chat.entity.ChatMessage;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

public interface ChatMessageRepository extends JpaRepository<ChatMessage, Long> {
    List<ChatMessage> findByThreadIdOrderByCreatedAtAsc(String threadId);
    void deleteByThreadId(String threadId);
}
