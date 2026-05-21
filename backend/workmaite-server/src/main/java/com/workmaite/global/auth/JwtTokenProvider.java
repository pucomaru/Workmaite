package com.workmaite.global.auth;

import com.workmaite.global.exception.BusinessException;
import com.workmaite.global.exception.ErrorCode;
import io.jsonwebtoken.*;
import io.jsonwebtoken.security.Keys;
import jakarta.annotation.PostConstruct;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.security.Key;
import java.util.Base64;
import java.util.Date;

/**
 * JWT 토큰 발급 / 검증 / 파싱
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class JwtTokenProvider {

    @Value("${jwt.secret}")
    private String secretKey;

    @Value("${jwt.access-token-expiration}")
    private long accessTokenExpiration;

    @Value("${jwt.refresh-token-expiration}")
    private long refreshTokenExpiration;

    private Key key;

    // Bean 생성 후 secret key 초기화
    @PostConstruct
    protected void init() {
        byte[] keyBytes = Base64.getEncoder().encode(secretKey.getBytes());
        this.key = Keys.hmacShaKeyFor(keyBytes);
    }

    // Access Token 발급
    public String createAccessToken(Long userId) {
        return createToken(userId, accessTokenExpiration);
    }

    // Refresh Token 발급
    public String createRefreshToken(Long userId) {
        return createToken(userId, refreshTokenExpiration);
    }

    // 토큰 생성 공통 로직
    private String createToken(Long userId, long expiration) {
        Date now = new Date();
        Date expiredAt = new Date(now.getTime() + expiration);

        return Jwts.builder()
                .setSubject(String.valueOf(userId))  // payload 에 userId 저장
                .setIssuedAt(now)                    // 발급 시간
                .setExpiration(expiredAt)            // 만료 시간
                .signWith(key, SignatureAlgorithm.HS256)
                .compact();
    }

    // 토큰에서 userId 추출
    public Long getUserId(String token) {
        return Long.parseLong(getClaims(token).getSubject());
    }

    // 토큰 유효성 검증
    public void validateToken(String token) {
        try {
            getClaims(token);
        } catch (ExpiredJwtException e) {
            throw new BusinessException(ErrorCode.EXPIRED_TOKEN);
        } catch (JwtException | IllegalArgumentException e) {
            throw new BusinessException(ErrorCode.INVALID_TOKEN);
        }
    }

    // 토큰 파싱
    private Claims getClaims(String token) {
        return Jwts.parserBuilder()
                .setSigningKey(key)
                .build()
                .parseClaimsJws(token)
                .getBody();
    }
}
