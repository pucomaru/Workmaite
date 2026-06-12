package com.workmaite.domain.auth.controller;

import com.workmaite.domain.auth.service.InvitationService;
import com.workmaite.global.common.ApiResponse;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

/**
 * 구성원 초대 API (P1-7②, MT-2)
 * POST /api/v1/invitations          - 초대 생성 (SYSTEM_ADMIN/COMPANY_ADMIN)
 * GET  /api/v1/invitations/{token}  - 초대 검증 (가입 폼 프리필, 공개)
 */
@RestController
@RequestMapping("/api/v1/invitations")
@RequiredArgsConstructor
public class InvitationController {

    private final InvitationService invitationService;

    @Getter
    @NoArgsConstructor
    public static class CreateRequest {
        @NotBlank @Email
        private String email;
        private String role; // USER | COMPANY_ADMIN
    }

    @PostMapping
    public ResponseEntity<ApiResponse<Map<String, Object>>> create(
            Authentication authentication,
            @RequestBody @jakarta.validation.Valid CreateRequest request) {
        Long inviterId = Long.parseLong(authentication.getName());
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(ApiResponse.ok(invitationService.create(inviterId, request.getEmail(), request.getRole())));
    }

    @GetMapping("/{token}")
    public ResponseEntity<ApiResponse<Map<String, Object>>> inspect(@PathVariable String token) {
        return ResponseEntity.ok(ApiResponse.ok(invitationService.inspect(token)));
    }
}
