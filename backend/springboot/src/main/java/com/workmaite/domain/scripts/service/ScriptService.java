package com.workmaite.domain.scripts.service;

import com.workmaite.domain.scripts.dto.ScriptResponse;
import com.workmaite.domain.scripts.dto.ScriptSaveRequest;
import com.workmaite.domain.scripts.dto.ScriptUpdateRequest;
import com.workmaite.domain.scripts.entity.SttSegment;
import com.workmaite.domain.scripts.repository.ScriptRepository;
import com.workmaite.global.audit.AuditLogged;
import com.workmaite.global.auth.MeetingAccessGuard;
import com.workmaite.global.exception.BusinessException;
import com.workmaite.global.exception.ErrorCode;
import java.util.List;
import lombok.RequiredArgsConstructor;
import org.springframework.data.domain.PageRequest;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class ScriptService {

  private final ScriptRepository scriptRepository;
  private final MeetingAccessGuard meetingAccessGuard;

  @Transactional
  public List<ScriptResponse> saveScripts(Long sessionId, ScriptSaveRequest request) {
    // STT 전사본은 회의체 운영물 — 간사/회사관리자/시스템관리자만 기록·수정
    meetingAccessGuard.requireMeetingEdit(meetingAccessGuard.meetingIdOfSession(sessionId));
    List<SttSegment> segments =
        request.getSegments().stream()
            .map(
                seg ->
                    SttSegment.builder()
                        .sessionId(sessionId)
                        .speakerLabel(seg.getSpeakerLabel())
                        .speakerUserId(seg.getSpeakerUserId())
                        .content(seg.getContent())
                        .startSec(seg.getStartSec())
                        .endSec(seg.getEndSec())
                        .confidence(seg.getConfidence())
                        .build())
            .toList();

    return scriptRepository.saveAll(segments).stream().map(ScriptResponse::from).toList();
  }

  private static final int MAX_PAGE_SIZE = 500;

  /**
   * STT 세그먼트 조회 (P8-3 keyset). limit 미지정 시 기존 전체 반환(호환 모드). afterSec 지정 시 그 이후 발화부터 limit개 — 증분
   * 로드용.
   */
  public List<ScriptResponse> getScripts(Long sessionId, Double afterSec, Integer limit) {
    meetingAccessGuard.requireViewBySession(sessionId);
    if (limit == null && afterSec == null) {
      return scriptRepository.findBySessionIdOrderByStartSecAsc(sessionId).stream()
          .map(ScriptResponse::from)
          .toList();
    }
    int size = Math.min(limit == null ? MAX_PAGE_SIZE : Math.max(limit, 1), MAX_PAGE_SIZE);
    return scriptRepository
        .findBySessionIdAndStartSecGreaterThanOrderByStartSecAsc(
            sessionId, afterSec == null ? Double.valueOf(-1.0) : afterSec, PageRequest.of(0, size))
        .stream()
        .map(ScriptResponse::from)
        .toList();
  }

  @Transactional
  public List<ScriptResponse> updateScripts(Long sessionId, ScriptUpdateRequest request) {
    meetingAccessGuard.requireMeetingEdit(meetingAccessGuard.meetingIdOfSession(sessionId));
    return request.getSegments().stream()
        .map(
            seg -> {
              SttSegment segment =
                  scriptRepository
                      .findById(seg.getId())
                      .orElseThrow(() -> new BusinessException(ErrorCode.SCRIPT_NOT_FOUND));

              // IDOR 방지: 세그먼트가 요청 세션 소속인지 검증
              if (!segment.getSessionId().equals(sessionId)) {
                throw new BusinessException(ErrorCode.SCRIPT_SESSION_MISMATCH);
              }

              segment.update(
                  seg.getSpeakerLabel(),
                  seg.getSpeakerUserId(),
                  seg.getContent(),
                  seg.getStartSec(),
                  seg.getEndSec());
              return ScriptResponse.from(segment);
            })
        .toList();
  }

  @Transactional
  @AuditLogged(action = "DELETE", entityType = "script")
  public void deleteScripts(Long sessionId) {
    meetingAccessGuard.requireMeetingEdit(meetingAccessGuard.meetingIdOfSession(sessionId));
    scriptRepository.deleteAllBySessionId(sessionId);
  }
}
