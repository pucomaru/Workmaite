package com.workmaite.domain.chat.repository;

import com.workmaite.domain.chat.entity.ChatMessage;
import java.util.List;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;

public interface ChatMessageRepository extends JpaRepository<ChatMessage, Integer> {
  List<ChatMessage> findByThreadIdOrderByCreatedAtAsc(String threadId);

  // keyset 페이지네이션 (P8-2): id 내림차순으로 beforeId 이전 메시지 limit개 (호출측에서 역순 정렬)
  List<ChatMessage> findByThreadIdAndIdLessThanOrderByIdDesc(
      String threadId, Integer beforeId, Pageable pageable);

  List<ChatMessage> findByThreadIdOrderByIdDesc(String threadId, Pageable pageable);

  void deleteByThreadId(String threadId);
}
