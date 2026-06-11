package com.workmaite.domain.chat.controller;

import com.workmaite.domain.chat.dto.ChatMessageResponse;
import com.workmaite.domain.chat.service.ChatMessageService;
import com.workmaite.global.common.ApiResponse;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.*;

import java.util.List;

@RestController
@RequestMapping("/api/v1")
@RequiredArgsConstructor
public class ChatMessageController {

    private final ChatMessageService chatMessageService;

    /**
     * GET /api/v1/chat/messages?threadId=meeting_1
     * thread_id 기준 채팅 히스토리 조회 (시간 오름차순)
     */
    @GetMapping("/chat/messages")
    public ResponseEntity<ApiResponse<List<ChatMessageResponse>>> getChatHistory(
            Authentication authentication,
            @RequestParam String threadId) {
        Long userId = Long.parseLong(authentication.getName());
        if (!isAccessible(threadId, userId)) {
            return ResponseEntity.status(HttpStatus.FORBIDDEN)
                    .body(ApiResponse.fail("접근 권한이 없습니다."));
        }
        return ResponseEntity.ok(ApiResponse.ok(chatMessageService.getHistory(threadId)));
    }

    /**
     * DELETE /api/v1/chat/messages?threadId=meeting_1
     * 새 채팅 시작 — thread의 모든 메시지 삭제
     */
    @DeleteMapping("/chat/messages")
    public ResponseEntity<ApiResponse<Void>> clearChatHistory(
            Authentication authentication,
            @RequestParam String threadId) {
        Long userId = Long.parseLong(authentication.getName());
        if (!isAccessible(threadId, userId)) {
            return ResponseEntity.status(HttpStatus.FORBIDDEN)
                    .body(ApiResponse.fail("접근 권한이 없습니다."));
        }
        chatMessageService.clearThread(threadId);
        return ResponseEntity.ok(ApiResponse.ok(null));
    }

    /**
     * global_{userId} 스레드는 본인만 접근 가능.
     * meeting_{meetingId} 스레드는 인증된 사용자에게 허용 (AI 백엔드가 멤버 권한 체크).
     */
    private boolean isAccessible(String threadId, Long userId) {
        if (threadId.startsWith("global_")) {
            try {
                return Long.parseLong(threadId.substring("global_".length())) == userId;
            } catch (NumberFormatException e) {
                return false;
            }
        }
        return threadId.startsWith("meeting_");
    }
}
