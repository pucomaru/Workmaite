package com.workmaite.domain.chat.repository;

import com.workmaite.domain.chat.entity.ChatMessage;
import java.util.List;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface ChatMessageRepository extends JpaRepository<ChatMessage, Long> {
  List<ChatMessage> findByThreadIdOrderByCreatedAtAsc(String threadId);

  // keyset 페이지네이션 (P8-2): id 내림차순으로 beforeId 이전 메시지 limit개 (호출측에서 역순 정렬)
  List<ChatMessage> findByThreadIdAndIdLessThanOrderByIdDesc(
      String threadId, Long beforeId, Pageable pageable);

  List<ChatMessage> findByThreadIdOrderByIdDesc(String threadId, Pageable pageable);

  void deleteByThreadId(String threadId);

  // 세션 삭제 시 챗 메시지는 보존하고 세션 링크만 해제한다 (대화 이력 유지).
  // 행을 지우지 않으므로 chat_feedback(chat_messages.id 참조)도 그대로 보존된다.
  @Modifying
  @Query("UPDATE ChatMessage c SET c.sessionId = null WHERE c.sessionId = :sessionId")
  void detachSession(@Param("sessionId") Long sessionId);

  // 회의체 삭제 시에도 대화는 보존하고 회의체 링크만 해제한다.
  @Modifying
  @Query("UPDATE ChatMessage c SET c.meetingId = null WHERE c.meetingId = :meetingId")
  void detachMeeting(@Param("meetingId") Long meetingId);
}
