package com.workmaite.domain.agendas.service;

import com.workmaite.domain.agendas.dto.*;
import com.workmaite.domain.agendas.entity.Agenda;
import com.workmaite.domain.agendas.repository.AgendaRepository;
import com.workmaite.global.audit.AuditLogged;
import com.workmaite.global.auth.MeetingAccessGuard;
import com.workmaite.global.exception.BusinessException;
import com.workmaite.global.exception.ErrorCode;
import com.workmaite.global.sync.NeoSyncService;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;

@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class AgendaService {

    private final AgendaRepository agendaRepository;
    private final NeoSyncService neoSyncService;
    private final MeetingAccessGuard meetingAccessGuard;

    public List<AgendaResponse> getAgendas(Long meetingId) {
        meetingAccessGuard.requireMember(meetingId);
        return agendaRepository.findByMeetingIdOrderByCreatedAt(meetingId).stream()
                .map(AgendaResponse::from)
                .toList();
    }

    @Transactional
    @AuditLogged(action = "CREATE", entityType = "agenda")
    public AgendaResponse createAgenda(Long meetingId, AgendaCreateRequest request) {
        meetingAccessGuard.requireMember(meetingId);
        Agenda agenda = Agenda.create(
                meetingId,
                request.getSessionId(),
                request.getTitle(),
                request.getPriority()
        );
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
        Agenda agenda = findAgendaById(agendaId);
        agenda.update(request.getTitle(), request.getStatus(), request.getDepartment(), request.getDueDate(), request.getPriority());
        neoSyncService.syncAgenda(agendaId);
        return AgendaResponse.from(agenda);
    }

    @Transactional
    @AuditLogged(action = "DELETE", entityType = "agenda")
    public void deleteAgenda(Long agendaId) {
        agendaRepository.delete(findAgendaById(agendaId));
    }

    @Transactional
    @AuditLogged(action = "ASSIGN", entityType = "agenda")
    public AgendaResponse assignAgenda(Long agendaId, AgendaAssignmentRequest request) {
        Agenda agenda = findAgendaById(agendaId);
        agenda.assign(request.getAssigneeId());
        neoSyncService.syncAgenda(agendaId);
        return AgendaResponse.from(agenda);
    }

    // 모든 agendaId 경로의 단일 진입점 — 멤버십 검증 포함 (IDOR 차단, P1-4)
    private Agenda findAgendaById(Long agendaId) {
        Agenda agenda = agendaRepository.findById(agendaId)
                .orElseThrow(() -> new BusinessException(ErrorCode.AGENDA_NOT_FOUND));
        meetingAccessGuard.requireMember(agenda.getMeetingId());
        return agenda;
    }
}
