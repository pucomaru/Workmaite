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
        com.workmaite.domain.user.entity.User user = userRepository.findById(Long.parseLong(userId))
                .orElseThrow(() -> new BusinessException(ErrorCode.USER_NOT_FOUND));

        var builder = User.builder()
                .username(String.valueOf(user.getId()))
                .password("")
                .roles(user.getRole() != null ? user.getRole().name() : "USER");
        if (user.isMustChangePassword()) {
            // 임시 비밀번호 상태 — MustChangePasswordFilter가 변경 전 API 사용을 차단 (P1-7②)
            builder.authorities("ROLE_" + (user.getRole() != null ? user.getRole().name() : "USER"),
                    "MUST_CHANGE_PASSWORD");
        }
        return builder.build();
    }
}
