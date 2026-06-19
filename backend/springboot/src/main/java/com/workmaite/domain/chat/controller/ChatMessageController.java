package com.workmaite.domain.chat.controller;

import com.workmaite.domain.chat.dto.ChatMessageResponse;
import com.workmaite.domain.chat.service.ChatMessageService;
import com.workmaite.global.auth.MeetingAccessGuard;
import com.workmaite.global.common.ApiResponse;
import com.workmaite.global.exception.BusinessException;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.util.List;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@Tag(name = "에이전트 채팅 이력", description = "AI 에이전트 채팅 스레드의 메시지 이력 조회 및 초기화 API")
@RestController
@RequestMapping("/api/v1")
@RequiredArgsConstructor
public class ChatMessageController {

  private final ChatMessageService chatMessageService;
  private final MeetingAccessGuard meetingAccessGuard;

  @Operation(
      summary = "채팅 히스토리 조회",
      description =
          "threadId 기준 채팅 메시지 이력을 시간 오름차순으로 조회합니다. keyset 페이지네이션 파라미터로 beforeId(이 메시지 ID 이전부터)와"
              + " limit(최대 반환 개수)을 선택적으로 지정할 수 있습니다. global_/archive_ 스레드는 본인만, meeting_/session_"
              + " 스레드는 해당 회의체 조회 권한이 있어야 접근 가능하며, 권한이 없으면 403 Forbidden(ApiResponse.fail)을 반환합니다.")
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

  @Operation(
      summary = "채팅 히스토리 초기화",
      description =
          "새 채팅을 시작하기 위해 해당 threadId의 모든 메시지를 삭제합니다. global_/archive_ 스레드는 본인만,"
              + " meeting_/session_ 스레드는 해당 회의체 조회 권한이 있어야 접근 가능하며, 권한이 없으면 403"
              + " Forbidden(ApiResponse.fail)을 반환합니다.")
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
