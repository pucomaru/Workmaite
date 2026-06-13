package com.workmaite.global.auth;

import com.workmaite.global.exception.BusinessException;
import com.workmaite.global.exception.ErrorCode;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;

/**
 * SecurityContext에서 현재 사용자 정보를 꺼내는 헬퍼. JwtAuthenticationFilter가 principal username에 userId를 저장하는
 * 규약에 의존한다.
 */
public final class CurrentUser {

  private CurrentUser() {}

  public static Integer idOrNull() {
    Authentication auth = SecurityContextHolder.getContext().getAuthentication();
    if (auth == null || auth.getName() == null || "anonymousUser".equals(auth.getName())) {
      return null;
    }
    try {
      return Integer.parseInt(auth.getName());
    } catch (NumberFormatException e) {
      return null;
    }
  }

  public static Integer id() {
    Integer id = idOrNull();
    if (id == null) {
      throw new BusinessException(ErrorCode.UNAUTHORIZED);
    }
    return id;
  }

  public static boolean isSystemAdmin() {
    Authentication auth = SecurityContextHolder.getContext().getAuthentication();
    return auth != null
        && auth.getAuthorities().stream()
            .anyMatch(a -> "ROLE_SYSTEM_ADMIN".equals(a.getAuthority()));
  }
}
