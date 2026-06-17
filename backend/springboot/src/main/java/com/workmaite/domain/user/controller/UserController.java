package com.workmaite.domain.user.controller;

import com.workmaite.domain.user.dto.UpdateUserRequest;
import com.workmaite.domain.user.dto.UserResponse;
import com.workmaite.domain.user.service.UserService;
import com.workmaite.global.common.ApiResponse;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * 사용자 정보 관련 API GET /api/v1/users/me - 내 정보 조회 PATCH /api/v1/users/me - 회원정보 수정 GET
 * /api/v1/users/search - 사용자 검색 (?q=) GET /api/v1/users - 전체 사용자 목록 PATCH /api/v1/users/{id} - 특정
 * 사용자 정보 수정 (관리자)
 */
@Tag(name = "사용자/조직", description = "내 정보·사용자 검색·구성원 관리·조직 권한 등 사용자/조직 관련 API")
@RestController
@RequestMapping("/api/v1/users")
@RequiredArgsConstructor
public class UserController {

  private final UserService userService;

  @Operation(summary = "내 정보 조회", description = "JWT에서 추출한 userId로 인증된 본인의 정보를 조회한다.")
  @GetMapping("/me")
  public ResponseEntity<ApiResponse<UserResponse>> getMe(Authentication authentication) {
    Long userId = Long.parseLong(authentication.getName());
    return ResponseEntity.ok(ApiResponse.ok(userService.getMe(userId)));
  }

  @Operation(summary = "내 정보 수정", description = "인증된 본인의 정보를 수정한다. 조직·부서·직위·비밀번호를 변경할 수 있다.")
  @PatchMapping("/me")
  public ResponseEntity<ApiResponse<UserResponse>> updateMe(
      Authentication authentication, @Valid @RequestBody UpdateUserRequest request) {
    Long userId = Long.parseLong(authentication.getName());
    return ResponseEntity.ok(ApiResponse.ok(userService.updateMe(userId, request)));
  }

  @Operation(
      summary = "사용자 검색",
      description = "이름 또는 이메일(q)로 사용자를 검색한다. 내 회사와 공유 회의체 범위로 제한되며 페이지네이션을 지원한다.")
  @GetMapping("/search")
  public ResponseEntity<ApiResponse<List<UserResponse>>> searchUsers(
      Authentication authentication,
      @RequestParam String q,
      @RequestParam(required = false) Integer page,
      @RequestParam(required = false) Integer size) {
    Long callerId = Long.parseLong(authentication.getName());
    return ResponseEntity.ok(ApiResponse.ok(userService.searchUsers(callerId, q, page, size)));
  }

  @Operation(
      summary = "ID 목록으로 사용자 조회",
      description = "쉼표로 구분된 ID 목록으로 사용자를 조회한다. 편집 모달 참석자 미리채우기용이며 가시성 범위로 제한된다.")
  @GetMapping("/by-ids")
  public ResponseEntity<ApiResponse<List<UserResponse>>> getUsersByIds(
      Authentication authentication, @RequestParam String ids) {
    Long callerId = Long.parseLong(authentication.getName());
    List<Long> idList =
        Arrays.stream(ids.split(","))
            .map(String::trim)
            .filter(s -> !s.isEmpty())
            .map(Long::parseLong)
            .collect(Collectors.toList());
    return ResponseEntity.ok(ApiResponse.ok(userService.getUsersByIds(callerId, idList)));
  }

  @Operation(
      summary = "사용자 목록 조회",
      description = "사용자 목록을 조회한다. 내 회사와 공유 회의체 범위로 제한되며 페이지네이션을 지원한다.")
  @GetMapping
  public ResponseEntity<ApiResponse<List<UserResponse>>> getAllUsers(
      Authentication authentication,
      @RequestParam(required = false) Integer page,
      @RequestParam(required = false) Integer size) {
    Long callerId = Long.parseLong(authentication.getName());
    return ResponseEntity.ok(ApiResponse.ok(userService.getAllUsers(callerId, page, size)));
  }

  @Operation(
      summary = "조직 권한 변경",
      description =
          "사용자의 조직 권한(COMPANY_ADMIN)을 부여·회수한다. SYSTEM_ADMIN만 호출할 수 있다. "
              + "본문 키는 기존대로 role을 사용하며 신규 company_role도 허용한다.")
  @PatchMapping("/{userId}/role")
  public ResponseEntity<ApiResponse<UserResponse>> updateCompanyRole(
      Authentication authentication,
      @PathVariable Long userId,
      @RequestBody Map<String, String> body) {
    Long callerId = Long.parseLong(authentication.getName());
    String companyRole = body.getOrDefault("role", body.getOrDefault("company_role", ""));
    return ResponseEntity.ok(
        ApiResponse.ok(userService.updateCompanyRole(callerId, userId, companyRole)));
  }

  @Operation(
      summary = "구성원 일괄 생성",
      description =
          "여러 구성원을 일괄 생성한다. 임시 비밀번호가 발급되고 최초 로그인 시 변경이 강제된다. "
              + "SYSTEM_ADMIN 또는 COMPANY_ADMIN만 호출할 수 있다.")
  @PostMapping("/bulk")
  public ResponseEntity<ApiResponse<List<Map<String, Object>>>> createMembers(
      Authentication authentication, @RequestBody List<Map<String, String>> rows) {
    Long callerId = Long.parseLong(authentication.getName());
    return ResponseEntity.ok(ApiResponse.ok(userService.createMembers(callerId, rows)));
  }

  @Operation(
      summary = "특정 사용자 정보 수정",
      description =
          "특정 사용자의 정보를 수정한다. SYSTEM_ADMIN 또는 같은 회사 COMPANY_ADMIN만 호출할 수 있으며 비밀번호는 변경할 수 없다.")
  @PatchMapping("/{userId}")
  public ResponseEntity<ApiResponse<UserResponse>> updateUser(
      Authentication authentication,
      @PathVariable Long userId,
      @RequestBody UpdateUserRequest request) {
    Long callerId = Long.parseLong(authentication.getName());
    return ResponseEntity.ok(ApiResponse.ok(userService.updateUser(callerId, userId, request)));
  }
}
