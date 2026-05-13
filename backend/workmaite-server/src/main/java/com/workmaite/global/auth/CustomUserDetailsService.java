package com.workmaite.global.auth;

import com.workmaite.global.exception.BusinessException;
import com.workmaite.global.exception.ErrorCode;
import lombok.RequiredArgsConstructor;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.stereotype.Service;

/**
 * Spring Security 가 인증할 때 DB에서 유저를 조회하는 서비스
 * userId 로 유저를 찾아서 UserDetails 로 반환
 */
@Service
@RequiredArgsConstructor
public class CustomUserDetailsService implements UserDetailsService {

    // TODO: UserRepository 완성되면 주입 예정
    // private final UserRepository userRepository;

    @Override
    public UserDetails loadUserByUsername(String userId) throws UsernameNotFoundException {
        // TODO: 실제 DB 조회로 교체 예정
        // User user = userRepository.findById(Long.parseLong(userId))
        //         .orElseThrow(() -> new BusinessException(ErrorCode.USER_NOT_FOUND));

        return User.builder()
                .username(userId)
                .password("")
                .roles("USER")
                .build();
    }
}
