package com.workmaite.global.auth;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

/**
 * 임시 비밀번호 상태(must_change_password) 사용자의 API 사용을 차단한다 (P1-7②). 허용: 비밀번호 변경(PATCH /users/me), 내 정보
 * 조회, 인증 경로 — 변경 전까지 다른 기능 사용 불가(강제).
 */
@Component
public class MustChangePasswordFilter extends OncePerRequestFilter {

  @Override
  protected void doFilterInternal(
      HttpServletRequest request, HttpServletResponse response, FilterChain filterChain)
      throws ServletException, IOException {
    Authentication auth = SecurityContextHolder.getContext().getAuthentication();
    boolean mustChange =
        auth != null
            && auth.getAuthorities().stream()
                .anyMatch(a -> "MUST_CHANGE_PASSWORD".equals(a.getAuthority()));
    if (mustChange && !isAllowed(request)) {
      response.setStatus(403);
      response.setContentType("application/json;charset=UTF-8");
      response
          .getWriter()
          .write(
              "{\"success\":false,\"message\":\"임시 비밀번호 상태입니다. 비밀번호를 먼저 변경해주세요.\",\"code\":\"MUST_CHANGE_PASSWORD\"}");
      return;
    }
    filterChain.doFilter(request, response);
  }

  private boolean isAllowed(HttpServletRequest req) {
    String uri = req.getRequestURI();
    return uri.startsWith("/api/v1/auth/")
        || uri.equals("/api/v1/users/me")
        || uri.startsWith("/actuator");
  }
}
