package com.workmaite.domain.home.controller;

import com.workmaite.domain.home.dto.CalendarResponse;
import com.workmaite.domain.home.service.HomeService;
import com.workmaite.global.common.ApiResponse;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@Tag(name = "홈/캘린더", description = "홈 화면 캘린더 일정 조회 API")
@RestController
@RequestMapping("/api/v1/home")
@RequiredArgsConstructor
public class HomeController {

  private final HomeService homeService;

  @Operation(
      summary = "캘린더 일정 조회",
      description =
          "로그인한 사용자의 예정 세션 일정을 캘린더로 반환합니다. view(month/week/day 뷰 단위)와 date(기준 날짜)를 지정하며,"
              + " 본인 일정만 조회됩니다.")
  @GetMapping("/calendar")
  public ResponseEntity<ApiResponse<CalendarResponse>> getCalendar(
      @RequestParam String view, @RequestParam String date, Authentication authentication) {
    Long userId = Long.parseLong(authentication.getName());
    return ResponseEntity.ok(ApiResponse.ok(homeService.getCalendar(userId, view, date)));
  }
}
