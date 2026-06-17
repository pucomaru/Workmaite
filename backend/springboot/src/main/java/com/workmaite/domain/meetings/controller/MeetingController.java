package com.workmaite.domain.meetings.controller;

import com.workmaite.domain.meetings.dto.ActiveMeetingResponse;
import com.workmaite.domain.meetings.dto.MeetingCreateRequest;
import com.workmaite.domain.meetings.dto.MeetingDetailResponse;
import com.workmaite.domain.meetings.dto.MeetingMemberAddRequest;
import com.workmaite.domain.meetings.dto.MeetingMemberResponse;
import com.workmaite.domain.meetings.dto.MeetingMemberUpdateRequest;
import com.workmaite.domain.meetings.dto.MeetingResponse;
import com.workmaite.domain.meetings.dto.MeetingUpdateRequest;
import com.workmaite.domain.meetings.service.MeetingService;
import com.workmaite.global.common.ApiResponse;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import java.util.List;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * 회의체 관련 API GET /api/v1/me/meetings - 내 진행중인 회의체 목록 조회 GET /api/v1/meetings - 전체 회의체 목록 조회 / 키워드
 * 검색 POST /api/v1/meetings - 회의체 생성 (생성자 간사 자동 등록) GET /api/v1/meetings/{meetingId} - 회의체 상세 조회
 * (참여자 목록 포함) PATCH /api/v1/meetings/{meetingId} - 회의체 수정 (secretary 권한) POST
 * /api/v1/meetings/{meetingId}/members - 회의체 참여자 추가 (secretary 권한) DELETE
 * /api/v1/meetings/{meetingId}/members/{userId} - 회의체 참여자 삭제 (secretary 권한) PATCH
 * /api/v1/meetings/{meetingId}/members/{userId} - 회의체 참여자 역할 수정 (secretary 권한)
 */
@Tag(name = "회의체", description = "회의체 생성·조회·수정·삭제 및 참여자/권한 관리 API")
@RestController
@RequestMapping("/api/v1")
@RequiredArgsConstructor
public class MeetingController {

  private final MeetingService meetingService;

  @Operation(
      summary = "내 회의체 권한 조회",
      description = "인증된 사용자가 해당 회의체에서 갖는 회의 권한(meetingRole)을 조회한다. 권한이 없으면 빈 문자열을 반환한다.")
  @GetMapping("/meetings/{meetingId}/my-role")
  public ResponseEntity<ApiResponse<java.util.Map<String, Object>>> getMyMeetingRole(
      @PathVariable Long meetingId, Authentication authentication) {
    Long userId = Long.parseLong(authentication.getName());
    String meetingRole = meetingService.getMyMeetingRole(meetingId, userId);
    return ResponseEntity.ok(
        ApiResponse.ok(java.util.Map.of("role", meetingRole != null ? meetingRole : "")));
  }

  @Operation(summary = "내 진행중인 회의체 목록 조회", description = "인증된 사용자가 참여 중인 진행중 회의체 목록을 조회한다.")
  @GetMapping("/me/meetings")
  public ResponseEntity<ApiResponse<List<ActiveMeetingResponse>>> getMyActiveMeetings(
      Authentication authentication) {
    Long userId = Long.parseLong(authentication.getName());
    return ResponseEntity.ok(ApiResponse.ok(meetingService.getMyActiveMeetings(userId)));
  }

  @Operation(
      summary = "회의체 목록 조회",
      description = "회의체 목록을 조회한다. 키워드(keyword)로 검색할 수 있으며 페이지네이션을 지원한다.")
  @GetMapping("/meetings")
  public ResponseEntity<ApiResponse<List<MeetingResponse>>> getMeetings(
      Authentication authentication,
      @RequestParam(required = false) String keyword,
      @RequestParam(required = false) Integer page,
      @RequestParam(required = false) Integer size) {
    Long userId = Long.parseLong(authentication.getName());
    return ResponseEntity.ok(
        ApiResponse.ok(meetingService.getMeetings(userId, keyword, page, size)));
  }

  @Operation(
      summary = "회의체 생성",
      description = "새 회의체를 생성한다. 생성자가 간사(secretary)로 자동 등록되며 성공 시 201 Created를 반환한다.")
  @PostMapping("/meetings")
  public ResponseEntity<ApiResponse<MeetingResponse>> createMeeting(
      Authentication authentication, @RequestBody @Valid MeetingCreateRequest request) {
    Long requesterId = Long.parseLong(authentication.getName());
    return ResponseEntity.status(HttpStatus.CREATED)
        .body(ApiResponse.ok(meetingService.createMeeting(requesterId, request)));
  }

  @Operation(summary = "회의체 상세 조회", description = "회의체의 상세 정보를 참여자 목록과 함께 조회한다.")
  @GetMapping("/meetings/{meetingId}")
  public ResponseEntity<ApiResponse<MeetingDetailResponse>> getMeeting(
      @PathVariable Long meetingId) {
    return ResponseEntity.ok(ApiResponse.ok(meetingService.getMeeting(meetingId)));
  }

  @Operation(summary = "회의체 수정", description = "회의체 정보를 수정한다. 간사(secretary) 권한이 필요하다.")
  @PatchMapping("/meetings/{meetingId}")
  public ResponseEntity<ApiResponse<MeetingResponse>> updateMeeting(
      @PathVariable Long meetingId,
      Authentication authentication,
      @RequestBody MeetingUpdateRequest request) {
    Long requesterId = Long.parseLong(authentication.getName());
    return ResponseEntity.ok(
        ApiResponse.ok(meetingService.updateMeeting(meetingId, requesterId, request)));
  }

  @Operation(summary = "회의체 삭제", description = "회의체를 삭제한다. 하위 회의·안건 등이 함께 정리되는 파괴적 작업이므로 주의가 필요하다.")
  @DeleteMapping("/meetings/{meetingId}")
  public ResponseEntity<ApiResponse<Void>> deleteMeeting(@PathVariable Long meetingId) {
    meetingService.deleteMeeting(meetingId);
    return ResponseEntity.ok(ApiResponse.ok(null));
  }

  @Operation(summary = "회의체 참여자 목록 조회", description = "회의체에 속한 참여자 목록과 각자의 회의 권한을 조회한다.")
  @GetMapping("/meetings/{meetingId}/members")
  public ResponseEntity<ApiResponse<List<MeetingMemberResponse>>> getMembers(
      @PathVariable Long meetingId) {
    return ResponseEntity.ok(ApiResponse.ok(meetingService.findMembers(meetingId)));
  }

  @Operation(summary = "회의체 참여자 추가", description = "회의체에 참여자를 추가한다. 간사(secretary) 권한이 필요하다.")
  @PostMapping("/meetings/{meetingId}/members")
  public ResponseEntity<ApiResponse<MeetingMemberResponse>> addMember(
      @PathVariable Long meetingId,
      Authentication authentication,
      @RequestBody @Valid MeetingMemberAddRequest request) {
    Long requesterId = Long.parseLong(authentication.getName());
    return ResponseEntity.ok(
        ApiResponse.ok(meetingService.addMember(meetingId, requesterId, request)));
  }

  @Operation(summary = "회의체 참여자 삭제", description = "회의체에서 참여자를 제거한다. 간사(secretary) 권한이 필요하다.")
  @DeleteMapping("/meetings/{meetingId}/members/{memberId}")
  public ResponseEntity<ApiResponse<Void>> removeMember(
      @PathVariable Long meetingId, @PathVariable Long memberId, Authentication authentication) {
    Long requesterId = Long.parseLong(authentication.getName());
    meetingService.removeMember(meetingId, requesterId, memberId);
    return ResponseEntity.ok(ApiResponse.ok(null));
  }

  @Operation(
      summary = "회의체 참여자 역할 수정",
      description = "회의체 참여자의 회의 권한(역할)을 수정한다. 간사(secretary) 권한이 필요하다.")
  @PatchMapping("/meetings/{meetingId}/members/{memberId}")
  public ResponseEntity<ApiResponse<MeetingMemberResponse>> updateMemberRole(
      @PathVariable Long meetingId,
      @PathVariable Long memberId,
      Authentication authentication,
      @RequestBody @Valid MeetingMemberUpdateRequest request) {
    Long requesterId = Long.parseLong(authentication.getName());
    return ResponseEntity.ok(
        ApiResponse.ok(meetingService.updateMemberRole(meetingId, requesterId, memberId, request)));
  }
}
