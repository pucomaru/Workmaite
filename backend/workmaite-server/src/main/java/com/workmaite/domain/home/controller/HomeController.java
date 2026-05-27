package com.workmaite.domain.home.controller;

import com.workmaite.domain.home.dto.CalendarResponse;
import com.workmaite.domain.home.service.HomeService;
import com.workmaite.global.common.ApiResponse;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * 홈 화면 API
 * GET /api/v1/home/calendar - 일정 조회 (월/주/일)
 */
@RestController
@RequestMapping("/api/v1/home")
@RequiredArgsConstructor
public class HomeController {

    private final HomeService homeService;

    // 월/주/일 뷰로 로그인 유저의 예정 세션 일정 반환
    @GetMapping("/calendar")
    public ResponseEntity<ApiResponse<CalendarResponse>> getCalendar(
            @RequestParam String view,
            @RequestParam String date,
            Authentication authentication) {
        Long userId = Long.parseLong(authentication.getName());
        return ResponseEntity.ok(ApiResponse.ok(homeService.getCalendar(userId, view, date)));
    }
}
