package com.workmaite.domain.agendas.service;

import com.workmaite.domain.agendas.dto.*;
import com.workmaite.domain.agendas.entity.Agenda;
import com.workmaite.domain.agendas.repository.AgendaRepository;
import com.workmaite.global.exception.BusinessException;
import com.workmaite.global.exception.ErrorCode;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;

@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class AgendaService {

    private final AgendaRepository agendaRepository;

    public List<AgendaResponse> getAgendas(Long meetingId) {
        return agendaRepository.findByMeetingIdOrderByOrderIndex(meetingId).stream()
                .map(AgendaResponse::from)
                .toList();
    }

    @Transactional
    public AgendaResponse createAgenda(Long meetingId, AgendaCreateRequest request) {
        Agenda agenda = Agenda.create(
                meetingId,
                request.getTitle(),
                request.getContent(),
                request.getOrderIndex()
        );
        return AgendaResponse.from(agendaRepository.save(agenda));
    }

    @Transactional
    public List<AgendaResponse> extractAgendas(Long meetingId, AgendaExtractRequest request) {
        // TODO: AI 연동 후 실제 추출 로직 구현
        return List.of();
    }

    public AgendaResponse getAgenda(Long agendaId) {
        return AgendaResponse.from(findAgendaById(agendaId));
    }

    @Transactional
    public AgendaResponse updateAgenda(Long agendaId, AgendaUpdateRequest request) {
        Agenda agenda = findAgendaById(agendaId);
        agenda.update(request.getTitle(), request.getContent(), request.getOrderIndex(), request.getStatus());
        return AgendaResponse.from(agenda);
    }

    @Transactional
    public void deleteAgenda(Long agendaId) {
        agendaRepository.delete(findAgendaById(agendaId));
    }

    @Transactional
    public AgendaResponse assignAgenda(Long agendaId, AgendaAssignmentRequest request) {
        Agenda agenda = findAgendaById(agendaId);
        agenda.assign(request.getAssigneeId());
        return AgendaResponse.from(agenda);
    }

    private Agenda findAgendaById(Long agendaId) {
        return agendaRepository.findById(agendaId)
                .orElseThrow(() -> new BusinessException(ErrorCode.AGENDA_NOT_FOUND));
    }
}
