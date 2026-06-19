package com.workmaite.domain.chat.service;

import com.workmaite.domain.chat.dto.ChatMessageResponse;
import com.workmaite.domain.chat.repository.ChatMessageRepository;
import java.util.Collections;
import java.util.List;
import java.util.stream.Collectors;
import lombok.RequiredArgsConstructor;
import org.springframework.data.domain.PageRequest;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class ChatMessageService {

  private final ChatMessageRepository chatMessageRepository;

  private static final int MAX_PAGE_SIZE = 100;

  /**
   * 채팅 이력 조회 (P8-2 keyset). limit 미지정 시 기존 전체 반환(호환 모드 — 프론트 전환 후 기본 size 강제 예정). beforeId 지정 시 그
   * 이전(과거) 메시지 페이지를 반환한다. 결과는 항상 시간 오름차순.
   */
  public List<ChatMessageResponse> getHistory(String threadId, Long beforeId, Integer limit) {
    if (limit == null && beforeId == null) {
      return chatMessageRepository.findByThreadIdOrderByCreatedAtAsc(threadId).stream()
          .map(ChatMessageResponse::from)
          .collect(Collectors.toList());
    }
    int size = Math.min(limit == null ? MAX_PAGE_SIZE : Math.max(limit, 1), MAX_PAGE_SIZE);
    var page = PageRequest.of(0, size);
    var rows =
        beforeId != null
            ? chatMessageRepository.findByThreadIdAndIdLessThanOrderByIdDesc(
                threadId, beforeId, page)
            : chatMessageRepository.findByThreadIdOrderByIdDesc(threadId, page);
    var result = rows.stream().map(ChatMessageResponse::from).collect(Collectors.toList());
    Collections.reverse(result); // 표시용 시간 오름차순
    return result;
  }

  @Transactional
  public void clearThread(String threadId) {
    chatMessageRepository.deleteByThreadId(threadId);
  }
}
