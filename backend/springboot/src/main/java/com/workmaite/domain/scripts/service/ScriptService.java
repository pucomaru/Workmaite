package com.workmaite.domain.scripts.service;

import com.workmaite.domain.scripts.dto.ScriptSaveRequest;
import com.workmaite.domain.scripts.dto.ScriptResponse;
import com.workmaite.domain.scripts.dto.ScriptUpdateRequest;
import com.workmaite.domain.scripts.entity.SttSegment;
import com.workmaite.domain.scripts.repository.ScriptRepository;
import com.workmaite.global.exception.BusinessException;
import com.workmaite.global.exception.ErrorCode;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;

@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class ScriptService {

    private final ScriptRepository scriptRepository;

    // STT 세그먼트 일괄 저장 - 한 세션에 여러 세그먼트를 한 번에 저장
    @Transactional
    public List<ScriptResponse> saveScripts(Long sessionId, ScriptSaveRequest request) {
        List<SttSegment> segments = request.getSegments().stream()
                .map(seg -> SttSegment.builder()
                        .sessionId(sessionId)
                        .speakerLabel(seg.getSpeakerLabel())
                        .speakerUserId(seg.getSpeakerUserId())
                        .content(seg.getContent())
                        .startSec(seg.getStartSec())
                        .endSec(seg.getEndSec())
                        .confidence(seg.getConfidence())
                        .build())
                .toList();

        return scriptRepository.saveAll(segments).stream()
                .map(ScriptResponse::from)
                .toList();
    }

    // 세션의 STT 세그먼트 목록 조회 (발화 시작 시간 오름차순)
    public List<ScriptResponse> getScripts(Long sessionId) {
        return scriptRepository.findBySessionIdOrderByStartSecAsc(sessionId).stream()
                .map(ScriptResponse::from)
                .toList();
    }

    // 세그먼트 부분 수정 - 세그먼트 ID 목록을 받아 각각 업데이트
    @Transactional
    public List<ScriptResponse> updateScripts(Long sessionId, ScriptUpdateRequest request) {
        return request.getSegments().stream()
                .map(seg -> {
                    SttSegment segment = scriptRepository.findById(seg.getId())
                            .orElseThrow(() -> new BusinessException(ErrorCode.SCRIPT_NOT_FOUND));

                    // 요청한 sessionId와 세그먼트의 sessionId가 다를 경우 차단
                    if (!segment.getSessionId().equals(sessionId)) {
                        throw new BusinessException(ErrorCode.SCRIPT_SESSION_MISMATCH);
                    }

                    segment.update(seg.getSpeakerLabel(), seg.getSpeakerUserId(), seg.getContent(), seg.getStartSec(), seg.getEndSec());
                    return ScriptResponse.from(segment);
                })
                .toList();
    }

    // 세션의 모든 STT 세그먼트 삭제
    @Transactional
    public void deleteScripts(Long sessionId) {
        scriptRepository.deleteAllBySessionId(sessionId);
    }
}
