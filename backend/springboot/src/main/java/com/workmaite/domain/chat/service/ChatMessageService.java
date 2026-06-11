package com.workmaite.domain.chat.service;

import com.workmaite.domain.chat.dto.ChatMessageResponse;
import com.workmaite.domain.chat.repository.ChatMessageRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.stream.Collectors;

@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class ChatMessageService {

    private final ChatMessageRepository chatMessageRepository;

    public List<ChatMessageResponse> getHistory(String threadId) {
        return chatMessageRepository.findByThreadIdOrderByCreatedAtAsc(threadId)
                .stream()
                .map(ChatMessageResponse::from)
                .collect(Collectors.toList());
    }

    @Transactional
    public void clearThread(String threadId) {
        chatMessageRepository.deleteByThreadId(threadId);
    }
}
