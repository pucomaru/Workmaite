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

  // STT 세그먼트 일괄 저장 - 한 세션에 여러 세그먼트를 한 번에 저장
  @Transactional
  public List<ScriptResponse> saveScripts(Long sessionId, ScriptSaveRequest request) {
    meetingAccessGuard.requireMemberBySession(sessionId);
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

  // 세션의 STT 세그먼트 목록 조회 (발화 시작 시간 오름차순)
  private static final int MAX_PAGE_SIZE = 500;

  /**
   * STT 세그먼트 조회 (P8-3 keyset). limit 미지정 시 기존 전체 반환(호환 모드). afterSec 지정 시 그 이후 발화부터 limit개 — 증분
   * 로드용.
   */
  public List<ScriptResponse> getScripts(Long sessionId, Double afterSec, Integer limit) {
    meetingAccessGuard.requireMemberBySession(sessionId);
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

  // 세그먼트 부분 수정 - 세그먼트 ID 목록을 받아 각각 업데이트
  @Transactional
  public List<ScriptResponse> updateScripts(Long sessionId, ScriptUpdateRequest request) {
    meetingAccessGuard.requireMemberBySession(sessionId);
    return request.getSegments().stream()
        .map(
            seg -> {
              SttSegment segment =
                  scriptRepository
                      .findById(seg.getId())
                      .orElseThrow(() -> new BusinessException(ErrorCode.SCRIPT_NOT_FOUND));

              // 요청한 sessionId와 세그먼트의 sessionId가 다를 경우 차단
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

  // 세션의 모든 STT 세그먼트 삭제
  @Transactional
  @AuditLogged(action = "DELETE", entityType = "script")
  public void deleteScripts(Long sessionId) {
    meetingAccessGuard.requireMemberBySession(sessionId);
    scriptRepository.deleteAllBySessionId(sessionId);
  }
}
