package com.workmaite.domain.meetings.controller;

import com.workmaite.domain.meetings.dto.*;
import com.workmaite.domain.meetings.service.MeetingService;
import com.workmaite.global.common.ApiResponse;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.*;

import java.util.List;

/**
 * 회의체 관련 API
 * GET    /api/v1/me/meetings                            - 내 진행중인 회의체 목록 조회
 * GET    /api/v1/meetings                               - 전체 회의체 목록 조회 / 키워드 검색
 * POST   /api/v1/meetings                               - 회의체 생성 (생성자 간사 자동 등록)
 * GET    /api/v1/meetings/{meetingId}                   - 회의체 상세 조회 (참여자 목록 포함)
 * PATCH  /api/v1/meetings/{meetingId}                   - 회의체 수정 (secretary 권한)
 * POST   /api/v1/meetings/{meetingId}/members           - 회의체 참여자 추가 (secretary 권한)
 * DELETE /api/v1/meetings/{meetingId}/members/{userId}  - 회의체 참여자 삭제 (secretary 권한)
 * PATCH  /api/v1/meetings/{meetingId}/members/{userId}  - 회의체 참여자 역할 수정 (secretary 권한)
 */
@RestController
@RequestMapping("/api/v1")
@RequiredArgsConstructor
public class MeetingController {

    private final MeetingService meetingService;

    @GetMapping("/meetings/{meetingId}/my-role")
    public ResponseEntity<ApiResponse<java.util.Map<String, Object>>> getMyRole(
            @PathVariable Long meetingId,
            Authentication authentication) {
        Long userId = Long.parseLong(authentication.getName());
        String role = meetingService.getMyRole(meetingId, userId);
        return ResponseEntity.ok(ApiResponse.ok(java.util.Map.of("role", role != null ? role : "")));
    }

    @GetMapping("/me/meetings")
    public ResponseEntity<ApiResponse<List<ActiveMeetingResponse>>> getMyActiveMeetings(
            Authentication authentication) {
        Long userId = Long.parseLong(authentication.getName());
        return ResponseEntity.ok(ApiResponse.ok(meetingService.getMyActiveMeetings(userId)));
    }

    @GetMapping("/meetings")
    public ResponseEntity<ApiResponse<List<MeetingResponse>>> getMeetings(
            Authentication authentication,
            @RequestParam(required = false) String keyword) {
        Long userId = Long.parseLong(authentication.getName());
        return ResponseEntity.ok(ApiResponse.ok(meetingService.getMeetings(userId, keyword)));
    }

    // 회의체 생성 - 생성자를 간사로 자동 등록
    @PostMapping("/meetings")
    public ResponseEntity<ApiResponse<MeetingResponse>> createMeeting(
            Authentication authentication,
            @RequestBody @Valid MeetingCreateRequest request) {
        Long requesterId = Long.parseLong(authentication.getName());
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(ApiResponse.ok(meetingService.createMeeting(requesterId, request)));
    }

    @GetMapping("/meetings/{meetingId}")
    public ResponseEntity<ApiResponse<MeetingDetailResponse>> getMeeting(
            @PathVariable Long meetingId) {
        return ResponseEntity.ok(ApiResponse.ok(meetingService.getMeeting(meetingId)));
    }

    @PatchMapping("/meetings/{meetingId}")
    public ResponseEntity<ApiResponse<MeetingResponse>> updateMeeting(
            @PathVariable Long meetingId,
            Authentication authentication,
            @RequestBody MeetingUpdateRequest request) {
        Long requesterId = Long.parseLong(authentication.getName());
        return ResponseEntity.ok(ApiResponse.ok(meetingService.updateMeeting(meetingId, requesterId, request)));
    }

    @GetMapping("/meetings/{meetingId}/members")
    public ResponseEntity<ApiResponse<List<MeetingMemberResponse>>> getMembers(
            @PathVariable Long meetingId) {
        return ResponseEntity.ok(ApiResponse.ok(meetingService.findMembers(meetingId)));
    }

    @PostMapping("/meetings/{meetingId}/members")
    public ResponseEntity<ApiResponse<MeetingMemberResponse>> addMember(
            @PathVariable Long meetingId,
            Authentication authentication,
            @RequestBody @Valid MeetingMemberAddRequest request) {
        Long requesterId = Long.parseLong(authentication.getName());
        return ResponseEntity.ok(ApiResponse.ok(meetingService.addMember(meetingId, requesterId, request)));
    }

    @DeleteMapping("/meetings/{meetingId}/members/{memberId}")
    public ResponseEntity<ApiResponse<Void>> removeMember(
            @PathVariable Long meetingId,
            @PathVariable Long memberId,
            Authentication authentication) {
        Long requesterId = Long.parseLong(authentication.getName());
        meetingService.removeMember(meetingId, requesterId, memberId);
        return ResponseEntity.ok(ApiResponse.ok(null));
    }

    @PatchMapping("/meetings/{meetingId}/members/{memberId}")
    public ResponseEntity<ApiResponse<MeetingMemberResponse>> updateMemberRole(
            @PathVariable Long meetingId,
            @PathVariable Long memberId,
            Authentication authentication,
            @RequestBody @Valid MeetingMemberUpdateRequest request) {
        Long requesterId = Long.parseLong(authentication.getName());
        return ResponseEntity.ok(ApiResponse.ok(meetingService.updateMemberRole(meetingId, requesterId, memberId, request)));
    }
}
