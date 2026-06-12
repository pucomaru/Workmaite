package com.workmaite.domain.minutes.service;

import com.workmaite.domain.minutes.dto.*;
import com.workmaite.domain.minutes.entity.Minutes;
import com.workmaite.domain.minutes.entity.MinutesStatus;
import com.workmaite.domain.minutes.repository.MinutesRepository;
import com.workmaite.global.audit.AuditLogged;
import com.workmaite.global.auth.MeetingAccessGuard;
import com.workmaite.global.exception.BusinessException;
import com.workmaite.global.exception.ErrorCode;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class MinutesService {

    private final MinutesRepository minutesRepository;
    private final MeetingAccessGuard meetingAccessGuard;

    @Transactional
    @AuditLogged(action = "CREATE", entityType = "minutes")
    public MinutesResponse generateMinutes(Long sessionId, MinutesGenerateRequest request) {
        meetingAccessGuard.requireMemberBySession(sessionId);
        if (minutesRepository.existsBySessionId(sessionId)) {
            throw new BusinessException(ErrorCode.MINUTES_ALREADY_EXISTS);
        }

        Minutes minutes = Minutes.builder()
                .sessionId(sessionId)
                .contentOriginal(request.getContentOriginal())
                .fileName(request.getFileName())
                .filePath(request.getFilePath())
                .build();

        return MinutesResponse.of(minutesRepository.save(minutes));
    }

    public MinutesSummaryResponse getSummary(MinutesSummaryRequest request) {
        return MinutesSummaryResponse.of(request.getContentRaw());
    }

    public MinutesResponse getMinutes(Long sessionId) {
        return MinutesResponse.of(findBySessionIdOrThrow(sessionId));
    }

    @Transactional
    @AuditLogged(action = "UPDATE", entityType = "minutes")
    public MinutesResponse updateMinutes(Long sessionId, MinutesUpdateRequest request) {
        Minutes minutes = findBySessionIdOrThrow(sessionId);

        if (minutes.getStatus() == MinutesStatus.CONFIRMED) {
            throw new BusinessException(ErrorCode.MINUTES_ALREADY_CONFIRMED);
        }

        minutes.updateSummary(request.getContentSummary());
        return MinutesResponse.of(minutes);
    }

    @Transactional
    @AuditLogged(action = "CONFIRM", entityType = "minutes")
    public MinutesResponse confirmMinutes(Long sessionId, MinutesConfirmRequest request) {
        Minutes minutes = findBySessionIdOrThrow(sessionId);

        if (minutes.getStatus() == MinutesStatus.CONFIRMED) {
            throw new BusinessException(ErrorCode.MINUTES_ALREADY_CONFIRMED);
        }

        minutes.confirm(request.getContentSummary());
        return MinutesResponse.of(minutes);
    }

    // 모든 sessionId 경로의 단일 진입점 — 멤버십 검증 포함 (IDOR 차단, P1-4)
    private Minutes findBySessionIdOrThrow(Long sessionId) {
        meetingAccessGuard.requireMemberBySession(sessionId);
        return minutesRepository.findBySessionId(sessionId)
                .orElseThrow(() -> new BusinessException(ErrorCode.MINUTES_NOT_FOUND));
    }
}
