package com.workmaite.domain.chat.controller;

import com.workmaite.domain.chat.dto.ChatMessageResponse;
import com.workmaite.domain.chat.service.ChatMessageService;
import com.workmaite.global.auth.MeetingAccessGuard;
import com.workmaite.global.common.ApiResponse;
import com.workmaite.global.exception.BusinessException;
import java.util.List;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1")
@RequiredArgsConstructor
public class ChatMessageController {

  private final ChatMessageService chatMessageService;
  private final MeetingAccessGuard meetingAccessGuard;

  /** GET /api/v1/chat/messages?threadId=meeting_1 thread_id 기준 채팅 히스토리 조회 (시간 오름차순) */
  @GetMapping("/chat/messages")
  public ResponseEntity<ApiResponse<List<ChatMessageResponse>>> getChatHistory(
      Authentication authentication,
      @RequestParam String threadId,
      @RequestParam(required = false) Long beforeId,
      @RequestParam(required = false) Integer limit) {
    Long userId = Long.parseLong(authentication.getName());
    if (!isAccessible(threadId, userId)) {
      return ResponseEntity.status(HttpStatus.FORBIDDEN).body(ApiResponse.fail("접근 권한이 없습니다."));
    }
    return ResponseEntity.ok(
        ApiResponse.ok(chatMessageService.getHistory(threadId, beforeId, limit)));
  }

  /** DELETE /api/v1/chat/messages?threadId=meeting_1 새 채팅 시작 — thread의 모든 메시지 삭제 */
  @DeleteMapping("/chat/messages")
  public ResponseEntity<ApiResponse<Void>> clearChatHistory(
      Authentication authentication, @RequestParam String threadId) {
    Long userId = Long.parseLong(authentication.getName());
    if (!isAccessible(threadId, userId)) {
      return ResponseEntity.status(HttpStatus.FORBIDDEN).body(ApiResponse.fail("접근 권한이 없습니다."));
    }
    chatMessageService.clearThread(threadId);
    return ResponseEntity.ok(ApiResponse.ok(null));
  }

  /**
   * global_{userId}, archive_{userId} 스레드는 본인만. meeting_{meetingId}, session_{sessionId} 스레드는 해당
   * 회의체 조회 권한(멤버/회사관리자/시스템관리자)이 있어야 접근 가능 — 스레드 ID만 알면 타 회의체 대화가 노출되던 IDOR 차단.
   */
  private boolean isAccessible(String threadId, Long userId) {
    if (threadId.startsWith("global_") || threadId.startsWith("archive_")) {
      String prefix = threadId.startsWith("global_") ? "global_" : "archive_";
      try {
        return Long.parseLong(threadId.substring(prefix.length())) == userId;
      } catch (NumberFormatException e) {
        return false;
      }
    }
    try {
      if (threadId.startsWith("meeting_")) {
        meetingAccessGuard.requireView(Long.parseLong(threadId.substring("meeting_".length())));
        return true;
      }
      if (threadId.startsWith("session_")) {
        meetingAccessGuard.requireViewBySession(
            Long.parseLong(threadId.substring("session_".length())));
        return true;
      }
    } catch (NumberFormatException | BusinessException e) {
      return false;
    }
    return false;
  }
}
