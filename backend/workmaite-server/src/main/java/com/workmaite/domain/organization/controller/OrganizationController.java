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

@RestController
@RequiredArgsConstructor
@RequestMapping("/api/v1")
public class OrganizationController {

    private final OrganizationService organizationService;

    @GetMapping("/organization/members")
    public ResponseEntity<ApiResponse<Page<OrganizationMemberResponse>>> getMembers(
            @RequestParam(required = false) String keyword,
            @RequestParam(required = false) MemberRole role,
            @PageableDefault(size = 20, sort = "createdAt", direction = Sort.Direction.DESC) Pageable pageable) {
        return ResponseEntity.ok(ApiResponse.ok(organizationService.getMembers(keyword, role, pageable)));
    }

    @GetMapping("/meetings/{meetingId}/members")
    public ResponseEntity<ApiResponse<List<OrganizationMemberResponse>>> getMembersByMeeting(
            @PathVariable Long meetingId) {
        return ResponseEntity.ok(ApiResponse.ok(organizationService.getMembersByMeeting(meetingId)));
    }

    @PatchMapping("/organization/members/{userId}")
    public ResponseEntity<ApiResponse<OrganizationMemberResponse>> updateMember(
            @PathVariable Long userId,
            @RequestBody @Valid OrganizationMemberUpdateRequest request) {
        return ResponseEntity.ok(ApiResponse.ok(organizationService.updateMember(userId, request)));
    }

    @DeleteMapping("/organization/members/{userId}")
    public ResponseEntity<ApiResponse<Void>> deleteMember(
            @PathVariable Long userId) {
        organizationService.deleteMember(userId);
        return ResponseEntity.ok(ApiResponse.ok(null));
    }
}
