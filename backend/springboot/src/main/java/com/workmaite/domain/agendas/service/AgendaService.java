package com.workmaite.domain.agendas.service;

import com.workmaite.domain.agendas.dto.AgendaAssignmentRequest;
import com.workmaite.domain.agendas.dto.AgendaCreateRequest;
import com.workmaite.domain.agendas.dto.AgendaExtractRequest;
import com.workmaite.domain.agendas.dto.AgendaResponse;
import com.workmaite.domain.agendas.dto.AgendaUpdateRequest;
import com.workmaite.domain.agendas.entity.Agenda;
import com.workmaite.domain.agendas.repository.AgendaRepository;
import com.workmaite.global.audit.AuditLogged;
import com.workmaite.global.auth.MeetingAccessGuard;
import com.workmaite.global.exception.BusinessException;
import com.workmaite.global.exception.ErrorCode;
import com.workmaite.global.sync.NeoSyncService;
import java.util.List;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class AgendaService {

  private final AgendaRepository agendaRepository;
  private final NeoSyncService neoSyncService;
  private final MeetingAccessGuard meetingAccessGuard;

  public List<AgendaResponse> getAgendas(Long meetingId) {
    meetingAccessGuard.requireView(meetingId);
    return agendaRepository.findByMeetingIdOrderByCreatedAt(meetingId).stream()
        .map(AgendaResponse::from)
        .toList();
  }

  @Transactional
  @AuditLogged(action = "CREATE", entityType = "agenda")
  public AgendaResponse createAgenda(Long meetingId, AgendaCreateRequest request) {
    // 아젠다(회의체 안건) 생성은 회의체 운영 행위 — 간사/회사관리자/시스템관리자만
    meetingAccessGuard.requireMeetingEdit(meetingId);
    Agenda agenda =
        Agenda.create(meetingId, request.getSessionId(), request.getTitle(), request.getPriority());
    AgendaResponse response = AgendaResponse.from(agendaRepository.save(agenda));
    neoSyncService.syncAgenda(response.getId());
    return response;
  }

  @Transactional
  public List<AgendaResponse> extractAgendas(Long meetingId, AgendaExtractRequest request) {
    return List.of();
  }

  public AgendaResponse getAgenda(Long agendaId) {
    return AgendaResponse.from(findAgendaById(agendaId));
  }

  @Transactional
  @AuditLogged(action = "UPDATE", entityType = "agenda")
  public AgendaResponse updateAgenda(Long agendaId, AgendaUpdateRequest request) {
    Agenda agenda = fetchAgenda(agendaId);
    // 편집 — 담당자 본인 또는 간사/회사관리자/시스템관리자만
    meetingAccessGuard.requireOwnedEdit(agenda.getMeetingId(), agenda.getAssigneeId());
    agenda.update(
        request.getTitle(),
        request.getStatus(),
        request.getDepartment(),
        request.getDueDate(),
        request.getPriority());
    neoSyncService.syncAgenda(agendaId);
    return AgendaResponse.from(agenda);
  }

  @Transactional
  @AuditLogged(action = "DELETE", entityType = "agenda")
  public void deleteAgenda(Long agendaId) {
    Agenda agenda = fetchAgenda(agendaId);
    meetingAccessGuard.requireOwnedEdit(agenda.getMeetingId(), agenda.getAssigneeId());
    agendaRepository.delete(agenda);
    neoSyncService.deleteAgenda(agendaId);
  }

  @Transactional
  @AuditLogged(action = "ASSIGN", entityType = "agenda")
  public AgendaResponse assignAgenda(Long agendaId, AgendaAssignmentRequest request) {
    Agenda agenda = fetchAgenda(agendaId);
    // 담당자 지정/변경은 회의체 운영 행위 — 간사/회사관리자/시스템관리자만
    meetingAccessGuard.requireMeetingEdit(agenda.getMeetingId());
    agenda.assign(request.getAssigneeId());
    neoSyncService.syncAgenda(agendaId);
    return AgendaResponse.from(agenda);
  }

  // 조회 단일 진입점 — 조회 권한 검증 포함 (IDOR 차단)
  private Agenda findAgendaById(Long agendaId) {
    Agenda agenda = fetchAgenda(agendaId);
    meetingAccessGuard.requireView(agenda.getMeetingId());
    return agenda;
  }

  // 가드 없는 원본 조회 — 호출부에서 view/edit 권한을 명시적으로 검증한다
  private Agenda fetchAgenda(Long agendaId) {
    return agendaRepository
        .findById(agendaId)
        .orElseThrow(() -> new BusinessException(ErrorCode.AGENDA_NOT_FOUND));
  }
}
