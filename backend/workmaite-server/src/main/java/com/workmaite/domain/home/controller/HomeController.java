package com.workmaite.domain.home.controller;

import com.workmaite.domain.home.dto.ActiveMeetingResponse;
import com.workmaite.domain.home.dto.CalendarResponse;
import com.workmaite.domain.home.dto.UpcomingSessionResponse;
import com.workmaite.domain.home.service.HomeService;
import com.workmaite.global.common.ApiResponse;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

/**
 * 홈 화면 API
 * GET /api/v1/home/meetings/active       - 로그인 유저의 진행중인 회의체 조회
 * GET /api/v1/home/sessions/upcoming     - 로그인 유저의 예정된 회의 조회
 * GET /api/v1/home/calendar              - 일정 조회 (월/주/일)
 */
@RestController
@RequiredArgsConstructor
@RequestMapping("/api/v1/home")
public class HomeController {

    private final HomeService homeService;

    @GetMapping("/meetings/active")
    public ResponseEntity<ApiResponse<List<ActiveMeetingResponse>>> getActiveMeetings(
            Authentication authentication) {
        Long userId = Long.parseLong(authentication.getName());
        return ResponseEntity.ok(ApiResponse.ok(homeService.getActiveMeetings(userId)));
    }

    @GetMapping("/sessions/upcoming")
    public ResponseEntity<ApiResponse<List<UpcomingSessionResponse>>> getUpcomingSessions(
            Authentication authentication) {
        Long userId = Long.parseLong(authentication.getName());
        return ResponseEntity.ok(ApiResponse.ok(homeService.getUpcomingSessions(userId)));
    }

    @GetMapping("/calendar")
    public ResponseEntity<ApiResponse<CalendarResponse>> getCalendar(
            @RequestParam String view,
            @RequestParam String date,
            Authentication authentication) {
        Long userId = Long.parseLong(authentication.getName());
        return ResponseEntity.ok(ApiResponse.ok(homeService.getCalendar(userId, view, date)));
    }
}
