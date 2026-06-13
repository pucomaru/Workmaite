package com.workmaite.global.auth;

import com.workmaite.global.exception.BusinessException;
import com.workmaite.global.exception.ErrorCode;
import io.jsonwebtoken.*;
import io.jsonwebtoken.security.Keys;
import jakarta.annotation.PostConstruct;
import java.nio.charset.StandardCharsets;
import java.security.Key;
import java.util.Date;
import java.util.UUID;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

/** JWT 토큰 발급 / 검증 / 파싱 */
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
  // FastAPI(python-jose)와 동일한 키 방식: 시크릿 문자열을 직접 바이트로 사용
  @PostConstruct
  protected void init() {
    byte[] keyBytes = secretKey.getBytes(StandardCharsets.UTF_8);
    this.key = Keys.hmacShaKeyFor(keyBytes);
  }

  // type 클레임 — refresh token을 access token으로 사용하는 공격 차단 (SEC-7)
  public static final String CLAIM_TYPE = "type";
  public static final String TYPE_ACCESS = "access";
  public static final String TYPE_REFRESH = "refresh";

  // Access Token 발급
  public String createAccessToken(Integer userId) {
    return createToken(userId, accessTokenExpiration, TYPE_ACCESS);
  }

  // Refresh Token 발급
  public String createRefreshToken(Integer userId) {
    return createToken(userId, refreshTokenExpiration, TYPE_REFRESH);
  }

  // 토큰 생성 공통 로직
  private String createToken(Integer userId, long expiration, String type) {
    Date now = new Date();
    Date expiredAt = new Date(now.getTime() + expiration);

    return Jwts.builder()
        .setSubject(String.valueOf(userId)) // payload 에 userId 저장
        .claim(CLAIM_TYPE, type)
        // jti: iat가 초 단위라 같은 초에 발급된 토큰이 byte-identical해지는 것 방지
        // (refresh 회전 시 신구 토큰이 같아지면 폐기가 무력화됨)
        .setId(UUID.randomUUID().toString())
        .setIssuedAt(now) // 발급 시간
        .setExpiration(expiredAt) // 만료 시간
        .signWith(key, SignatureAlgorithm.HS256)
        .compact();
  }

  // 토큰에서 userId 추출
  public Integer getUserId(String token) {
    return Integer.parseInt(getClaims(token).getSubject());
  }

  // 토큰 만료 시각 추출 (refresh token 저장용)
  public Date getExpiration(String token) {
    return getClaims(token).getExpiration();
  }

  /** API 인증용 access token 검증. type 클레임이 없는 구버전 토큰은 만료(15분) 전까지 access로 간주하고, refresh 토큰은 거부한다. */
  public void validateAccessToken(String token) {
    Claims claims = parseOrThrow(token);
    if (TYPE_REFRESH.equals(claims.get(CLAIM_TYPE))) {
      throw new BusinessException(ErrorCode.INVALID_TOKEN);
    }
  }

  // 갱신용 refresh token 검증 — type 클레임이 refresh인 토큰만 허용
  public void validateRefreshToken(String token) {
    Claims claims = parseOrThrow(token);
    if (!TYPE_REFRESH.equals(claims.get(CLAIM_TYPE))) {
      throw new BusinessException(ErrorCode.INVALID_TOKEN);
    }
  }

  private Claims parseOrThrow(String token) {
    try {
      return getClaims(token);
    } catch (ExpiredJwtException e) {
      throw new BusinessException(ErrorCode.EXPIRED_TOKEN);
    } catch (JwtException | IllegalArgumentException e) {
      throw new BusinessException(ErrorCode.INVALID_TOKEN);
    }
  }

  // 토큰 파싱
  private Claims getClaims(String token) {
    return Jwts.parserBuilder().setSigningKey(key).build().parseClaimsJws(token).getBody();
  }
}
