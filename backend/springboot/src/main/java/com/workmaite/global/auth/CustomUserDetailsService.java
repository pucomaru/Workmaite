package com.workmaite.global.auth;

import com.workmaite.domain.user.repository.UserRepository;
import com.workmaite.global.exception.BusinessException;
import com.workmaite.global.exception.ErrorCode;
import lombok.RequiredArgsConstructor;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.stereotype.Service;

@Service
@RequiredArgsConstructor
public class CustomUserDetailsService implements UserDetailsService {

  private final UserRepository userRepository;

  @Override
  public UserDetails loadUserByUsername(String userId) throws UsernameNotFoundException {
    com.workmaite.domain.user.entity.User user =
        userRepository
            .findById(Long.parseLong(userId))
            .orElseThrow(() -> new BusinessException(ErrorCode.USER_NOT_FOUND));

    // 탈퇴(소프트 삭제) 계정은 잔여 액세스 토큰으로도 인증 불가 (MT-6)
    if (!user.isActive()) {
      throw new BusinessException(ErrorCode.USER_NOT_FOUND);
    }

    var builder =
        User.builder()
            .username(String.valueOf(user.getId()))
            .password("")
            .roles(user.getCompanyRole() != null ? user.getCompanyRole().name() : "USER");
    if (user.isMustChangePassword()) {
      // 임시 비밀번호 상태 — MustChangePasswordFilter가 변경 전 API 사용을 차단 (P1-7②)
      builder.authorities(
          "ROLE_" + (user.getCompanyRole() != null ? user.getCompanyRole().name() : "USER"),
          "MUST_CHANGE_PASSWORD");
    }
    return builder.build();
  }
}
