package com.workmaite.domain.meetings.controller;

import com.workmaite.domain.meetings.dto.*;
import com.workmaite.domain.meetings.service.MeetingService;
import com.workmaite.global.common.ApiResponse;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.*;

import java.util.List;

/**
 * 회의체 관련 API
 * GET    /api/v1/meetings                              - 전체 회의체 목록 조회 / 키워드 검색
 * GET    /api/v1/meetings/{meetingId}                  - 회의체 상세 조회 (참여자 목록 포함)
 * PATCH  /api/v1/meetings/{meetingId}                  - 회의체 수정 (secretary 권한)
 * POST   /api/v1/meetings/{meetingId}/members          - 회의체 참여자 추가 (secretary 권한)
 * DELETE /api/v1/meetings/{meetingId}/members/{userId} - 회의체 참여자 삭제 (secretary 권한)
 * PATCH  /api/v1/meetings/{meetingId}/members/{userId} - 회의체 참여자 역할 수정 (secretary 권한)
 */
@RestController
@RequiredArgsConstructor
@RequestMapping("/api/v1/meetings")
public class MeetingController {

    private final MeetingService meetingService;

    // 목록 조회 - keyword 파라미터가 있으면 제목·목적 기준 검색
    @GetMapping
    public ResponseEntity<ApiResponse<List<MeetingResponse>>> getMeetings(
            @RequestParam(required = false) String keyword) {
        return ResponseEntity.ok(ApiResponse.ok(meetingService.getMeetings(keyword)));
    }

    // 상세 조회 - 참여자 목록 포함
    @GetMapping("/{meetingId}")
    public ResponseEntity<ApiResponse<MeetingDetailResponse>> getMeeting(
            @PathVariable Long meetingId) {
        return ResponseEntity.ok(ApiResponse.ok(meetingService.getMeeting(meetingId)));
    }

    // 회의체 수정 - secretary 권한 필요, null 필드는 변경 없음 (PATCH)
    @PatchMapping("/{meetingId}")
    public ResponseEntity<ApiResponse<MeetingResponse>> updateMeeting(
            @PathVariable Long meetingId,
            Authentication authentication,
            @RequestBody MeetingUpdateRequest request) {
        Long requesterId = Long.parseLong(authentication.getName());
        return ResponseEntity.ok(ApiResponse.ok(meetingService.updateMeeting(meetingId, requesterId, request)));
    }

    // 참여자 추가 - secretary 권한 필요, 동일 유저 중복 추가 불가
    @PostMapping("/{meetingId}/members")
    public ResponseEntity<ApiResponse<MeetingMemberResponse>> addMember(
            @PathVariable Long meetingId,
            Authentication authentication,
            @RequestBody @Valid MeetingMemberAddRequest request) {
        Long requesterId = Long.parseLong(authentication.getName());
        return ResponseEntity.ok(ApiResponse.ok(meetingService.addMember(meetingId, requesterId, request)));
    }

    // 참여자 삭제 - secretary 권한 필요
    @DeleteMapping("/{meetingId}/members/{userId}")
    public ResponseEntity<ApiResponse<Void>> removeMember(
            @PathVariable Long meetingId,
            @PathVariable Long userId,
            Authentication authentication) {
        Long requesterId = Long.parseLong(authentication.getName());
        meetingService.removeMember(meetingId, requesterId, userId);
        return ResponseEntity.ok(ApiResponse.ok(null));
    }

    // 참여자 역할 수정 - secretary 권한 필요
    @PatchMapping("/{meetingId}/members/{userId}")
    public ResponseEntity<ApiResponse<MeetingMemberResponse>> updateMemberRole(
            @PathVariable Long meetingId,
            @PathVariable Long userId,
            Authentication authentication,
            @RequestBody @Valid MeetingMemberUpdateRequest request) {
        Long requesterId = Long.parseLong(authentication.getName());
        return ResponseEntity.ok(ApiResponse.ok(meetingService.updateMemberRole(meetingId, requesterId, userId, request)));
    }
}
