package com.workmaite.domain.organization.controller;

import com.workmaite.domain.organization.dto.OrganizationMemberResponse;
import com.workmaite.domain.organization.dto.OrganizationMemberUpdateRequest;
import com.workmaite.domain.organization.entity.MemberRole;
import com.workmaite.domain.organization.service.OrganizationService;
import com.workmaite.global.common.ApiResponse;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.data.web.PageableDefault;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;

/**
 * 조직 구성원 관련 API
 * GET    /api/v1/organization/members              - 구성원 목록 조회 (키워드·역할 필터, 페이징)
 * GET    /api/v1/meetings/{meetingId}/members      - 회의체별 구성원 목록 조회
 * PATCH  /api/v1/organization/members/{userId}     - 구성원 역할 수정
 * DELETE /api/v1/organization/members/{userId}     - 구성원 삭제
 */
@RestController
@RequestMapping("/api/v1")
@RequiredArgsConstructor
public class OrganizationController {

    private final OrganizationService organizationService;

    // keyword(이름·이메일) 또는 role로 필터링, 없으면 전체 반환
    @GetMapping("/organization/members")
    public ResponseEntity<ApiResponse<Page<OrganizationMemberResponse>>> getMembers(
            @RequestParam(required = false) String keyword,
            @RequestParam(required = false) MemberRole role,
            @PageableDefault(size = 20, sort = "createdAt", direction = Sort.Direction.DESC) Pageable pageable) {
        return ResponseEntity.ok(ApiResponse.ok(organizationService.getMembers(keyword, role, pageable)));
    }

    // 특정 회의체에 속한 구성원 목록 조회
    @GetMapping("/meetings/{meetingId}/members")
    public ResponseEntity<ApiResponse<List<OrganizationMemberResponse>>> getMembersByMeeting(
            @PathVariable Long meetingId) {
        return ResponseEntity.ok(ApiResponse.ok(organizationService.getMembersByMeeting(meetingId)));
    }

    // 구성원 역할 수정
    @PatchMapping("/organization/members/{userId}")
    public ResponseEntity<ApiResponse<OrganizationMemberResponse>> updateMember(
            @PathVariable Long userId,
            @RequestBody @Valid OrganizationMemberUpdateRequest request) {
        return ResponseEntity.ok(ApiResponse.ok(organizationService.updateMember(userId, request)));
    }

    // 구성원 삭제
    @DeleteMapping("/organization/members/{userId}")
    public ResponseEntity<ApiResponse<Void>> deleteMember(
            @PathVariable Long userId) {
        organizationService.deleteMember(userId);
        return ResponseEntity.ok(ApiResponse.ok(null));
    }
}
