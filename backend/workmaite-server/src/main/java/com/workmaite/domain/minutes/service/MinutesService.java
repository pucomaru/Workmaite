package com.workmaite.domain.minutes.service;

import com.workmaite.domain.minutes.dto.*;
import com.workmaite.domain.minutes.entity.Minutes;
import com.workmaite.domain.minutes.entity.MinutesStatus;
import com.workmaite.domain.minutes.repository.MinutesRepository;
import com.workmaite.global.exception.BusinessException;
import com.workmaite.global.exception.ErrorCode;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 회의록 비즈니스 로직
 * - 생성: sessionId당 하나만 허용, AI가 contentRaw → contentOriginal 변환 (추후 연동)
 * - 수정: CONFIRMED 상태에서는 불가
 * - 확정: contentSummary 없으면 contentOriginal 그대로 확정
 * - 진행 중 요약: DB 저장 없이 AI 응답만 반환
 */
@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class MinutesService {

    private final MinutesRepository minutesRepository;

    // 회의록 생성 - sessionId당 하나만 허용
    @Transactional
    public MinutesResponse generateMinutes(Long sessionId, MinutesGenerateRequest request) {
        if (minutesRepository.existsBySessionId(sessionId)) {
            throw new BusinessException(ErrorCode.MINUTES_ALREADY_EXISTS);
        }

        // TODO: AI 호출하여 contentRaw → contentOriginal 생성
        String contentOriginal = request.getContentRaw();

        Minutes minutes = Minutes.builder()
                .sessionId(sessionId)
                .contentRaw(request.getContentRaw())
                .contentOriginal(contentOriginal)
                .build();

        return MinutesResponse.of(minutesRepository.save(minutes));
    }

    // 진행 중 요약 - DB 저장 없이 AI 응답만 반환
    public MinutesSummaryResponse getSummary(MinutesSummaryRequest request) {
        // TODO: AI 호출하여 중간 요약 생성
        String summary = request.getContentRaw();

        return MinutesSummaryResponse.of(summary);
    }

    public MinutesResponse getMinutes(Long sessionId) {
        return MinutesResponse.of(findBySessionIdOrThrow(sessionId));
    }

    // 수동 수정 - CONFIRMED 상태에서는 불가
    @Transactional
    public MinutesResponse updateMinutes(Long sessionId, MinutesUpdateRequest request) {
        Minutes minutes = findBySessionIdOrThrow(sessionId);

        if (minutes.getStatus() == MinutesStatus.CONFIRMED) {
            throw new BusinessException(ErrorCode.MINUTES_ALREADY_CONFIRMED);
        }

        minutes.updateSummary(request.getContentSummary());
        return MinutesResponse.of(minutes);
    }

    // 회의록 확정 - contentSummary 없으면 AI 생성본(contentOriginal) 그대로 확정
    @Transactional
    public MinutesResponse confirmMinutes(Long sessionId, MinutesConfirmRequest request) {
        Minutes minutes = findBySessionIdOrThrow(sessionId);

        if (minutes.getStatus() == MinutesStatus.CONFIRMED) {
            throw new BusinessException(ErrorCode.MINUTES_ALREADY_CONFIRMED);
        }

        minutes.confirm(request.getContentSummary());
        return MinutesResponse.of(minutes);
    }

    private Minutes findBySessionIdOrThrow(Long sessionId) {
        return minutesRepository.findBySessionId(sessionId)
                .orElseThrow(() -> new BusinessException(ErrorCode.MINUTES_NOT_FOUND));
    }
}
