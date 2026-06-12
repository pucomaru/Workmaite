package com.workmaite.global.auth;

import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.PBEKeySpec;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.HexFormat;

/**
 * 구 FastAPI 가입 사용자의 비밀번호 해시(`pbkdf2:{salt_hex}:{hash_hex}`) 검증.
 * FastAPI는 salt 16진수 문자열의 UTF-8 바이트를 그대로 salt로 사용했으므로 동일하게 처리한다.
 * 로그인 성공 시 BCrypt로 재해시하는 과도기 마이그레이션 전용 — FastAPI 발급 경로 제거(P1-1) 이후
 * 신규 해시는 생성되지 않으며, 전 사용자 전환이 끝나면 이 클래스는 삭제한다.
 */
public final class LegacyPbkdf2Verifier {

    private static final int ITERATIONS = 100_000;

    private LegacyPbkdf2Verifier() {
    }

    public static boolean isLegacy(String storedHash) {
        return storedHash != null && storedHash.startsWith("pbkdf2:");
    }

    public static boolean matches(String rawPassword, String storedHash) {
        try {
            String[] parts = storedHash.split(":");
            if (parts.length != 3) {
                return false;
            }
            byte[] expected = HexFormat.of().parseHex(parts[2]);
            PBEKeySpec spec = new PBEKeySpec(
                    rawPassword.toCharArray(),
                    parts[1].getBytes(StandardCharsets.UTF_8),
                    ITERATIONS,
                    expected.length * 8);
            byte[] actual = SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256")
                    .generateSecret(spec)
                    .getEncoded();
            return MessageDigest.isEqual(expected, actual);
        } catch (Exception e) {
            return false;
        }
    }
}
