package com.workmaite.domain.auth.service;

import com.workmaite.domain.auth.entity.Invitation;
import com.workmaite.domain.auth.repository.InvitationRepository;
import com.workmaite.domain.user.entity.User;
import com.workmaite.domain.user.entity.UserRole;
import com.workmaite.domain.user.repository.UserRepository;
import com.workmaite.global.audit.AuditLogService;
import com.workmaite.global.exception.BusinessException;
import com.workmaite.global.exception.ErrorCode;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.LocalDateTime;
import java.util.HexFormat;
import java.util.Map;
import java.util.UUID;

/**
 * 초대 기반 온보딩 (P1-7②, MT-2).
 * - 초대 생성: SYSTEM_ADMIN 또는 같은 회사 COMPANY_ADMIN. 토큰 평문은 응답으로 1회만 반환.
 * - 초대 조회/수락: 토큰 해시 대조, 만료·중복 수락 차단.
 */
@Service
@RequiredArgsConstructor
@Transactional
public class InvitationService {

    private static final int EXPIRY_DAYS = 7;

    private final InvitationRepository invitationRepository;
    private final UserRepository userRepository;
    private final AuditLogService auditLogService;

    /** 초대 생성 — 평문 토큰을 반환한다(저장은 해시만). */
    public Map<String, Object> create(Long inviterId, String email, String role) {
        User inviter = userRepository.findById(inviterId)
                .orElseThrow(() -> new BusinessException(ErrorCode.USER_NOT_FOUND));
        if (inviter.getRole() != UserRole.SYSTEM_ADMIN && inviter.getRole() != UserRole.COMPANY_ADMIN) {
            throw new BusinessException(ErrorCode.ACCESS_DENIED);
        }
        if (userRepository.existsByEmail(email)) {
            throw new BusinessException(ErrorCode.DUPLICATE_EMAIL);
        }
        String token = UUID.randomUUID().toString().replace("-", "")
                + UUID.randomUUID().toString().replace("-", "").substring(0, 8);
        Invitation inv = invitationRepository.save(Invitation.builder()
                .email(email)
                .companyId(inviter.getCompanyId())
                .invitedBy(inviterId)
                .tokenHash(sha256Hex(token))
                .role("COMPANY_ADMIN".equals(role) ? "COMPANY_ADMIN" : "USER")
                .expiresAt(LocalDateTime.now().plusDays(EXPIRY_DAYS))
                .build());
        auditLogService.record("INVITE", "user", inv.getId(), null,
                "{\"email\": \"" + email + "\"}");
        return Map.of(
                "id", inv.getId(),
                "email", email,
                "token", token,                 // 1회만 노출 — 초대 링크 구성용
                "expiresAt", inv.getExpiresAt().toString()
        );
    }

    /** 토큰 검증 후 가입 폼 프리필 정보 반환 (공개 엔드포인트용) */
    @Transactional(readOnly = true)
    public Map<String, Object> inspect(String token) {
        Invitation inv = findValid(token);
        return Map.of(
                "email", inv.getEmail(),
                "company", inv.getCompanyId() == null ? "" : String.valueOf(inv.getCompanyId())
        );
    }

    /** 가입 시 초대 수락 — 검증된 Invitation을 반환 (signup 트랜잭션 안에서 호출) */
    public Invitation accept(String token, String signupEmail) {
        Invitation inv = findValid(token);
        if (!inv.getEmail().equalsIgnoreCase(signupEmail)) {
            throw new BusinessException(ErrorCode.INVALID_INPUT_VALUE);
        }
        inv.accept();
        return inv;
    }

    private Invitation findValid(String token) {
        Invitation inv = invitationRepository.findByTokenHash(sha256Hex(token))
                .orElseThrow(() -> new BusinessException(ErrorCode.INVALID_TOKEN));
        if (inv.isExpired() || inv.isAccepted()) {
            throw new BusinessException(ErrorCode.EXPIRED_TOKEN);
        }
        return inv;
    }

    private static String sha256Hex(String value) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256")
                    .digest(value.getBytes(StandardCharsets.UTF_8)));
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException("SHA-256 미지원 JVM", e);
        }
    }
}
