package com.workmaite.domain.user.controller;

import com.workmaite.domain.user.dto.UpdateUserRequest;
import com.workmaite.domain.user.dto.UserResponse;
import com.workmaite.domain.user.service.UserService;
import com.workmaite.global.common.ApiResponse;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.*;

/**
 * 사용자 정보 관련 API
 * GET  /api/v1/users/me  - 내 정보 조회
 * PATCH /api/v1/users/me - 회원정보 수정
 */
@RestController
@RequestMapping("/api/v1/users")
@RequiredArgsConstructor
public class UserController {

    private final UserService userService;

    // 내 정보 조회 - JWT에서 추출한 userId로 조회
    @GetMapping("/me")
    public ResponseEntity<ApiResponse<UserResponse>> getMe(Authentication authentication) {
        Long userId = Long.parseLong(authentication.getName());
        return ResponseEntity.ok(ApiResponse.ok(userService.getMe(userId)));
    }

    // 회원정보 수정 - 조직, 부서, 직위, 비밀번호 변경 가능
    @PatchMapping("/me")
    public ResponseEntity<ApiResponse<UserResponse>> updateMe(
            Authentication authentication,
            @Valid @RequestBody UpdateUserRequest request) {
        Long userId = Long.parseLong(authentication.getName());
        return ResponseEntity.ok(ApiResponse.ok(userService.updateMe(userId, request)));
    }
}
