package com.workmaite.domain.agendas.controller;

import com.workmaite.domain.agendas.dto.*;
import com.workmaite.domain.agendas.service.AgendaService;
import com.workmaite.global.common.ApiResponse;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;

@RestController
@RequiredArgsConstructor
@RequestMapping("/api/v1")
public class AgendaController {

    private final AgendaService agendaService;

    @PostMapping("/meetings/{meetingId}/agendas/extract")
    public ResponseEntity<ApiResponse<List<AgendaResponse>>> extractAgendas(
            @PathVariable Long meetingId,
            @RequestBody @Valid AgendaExtractRequest request) {
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(ApiResponse.ok(agendaService.extractAgendas(meetingId, request)));
    }

    @GetMapping("/meetings/{meetingId}/agendas")
    public ResponseEntity<ApiResponse<List<AgendaResponse>>> getAgendas(
            @PathVariable Long meetingId) {
        return ResponseEntity.ok(ApiResponse.ok(agendaService.getAgendas(meetingId)));
    }

    @PostMapping("/meetings/{meetingId}/agendas")
    public ResponseEntity<ApiResponse<AgendaResponse>> createAgenda(
            @PathVariable Long meetingId,
            @RequestBody @Valid AgendaCreateRequest request) {
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(ApiResponse.ok(agendaService.createAgenda(meetingId, request)));
    }

    @GetMapping("/agendas/{agendaId}")
    public ResponseEntity<ApiResponse<AgendaResponse>> getAgenda(
            @PathVariable Long agendaId) {
        return ResponseEntity.ok(ApiResponse.ok(agendaService.getAgenda(agendaId)));
    }

    @PatchMapping("/agendas/{agendaId}")
    public ResponseEntity<ApiResponse<AgendaResponse>> updateAgenda(
            @PathVariable Long agendaId,
            @RequestBody AgendaUpdateRequest request) {
        return ResponseEntity.ok(ApiResponse.ok(agendaService.updateAgenda(agendaId, request)));
    }

    @DeleteMapping("/agendas/{agendaId}")
    public ResponseEntity<ApiResponse<Void>> deleteAgenda(
            @PathVariable Long agendaId) {
        agendaService.deleteAgenda(agendaId);
        return ResponseEntity.ok(ApiResponse.ok(null));
    }

    @PatchMapping("/agendas/{agendaId}/assignment")
    public ResponseEntity<ApiResponse<AgendaResponse>> assignAgenda(
            @PathVariable Long agendaId,
            @RequestBody @Valid AgendaAssignmentRequest request) {
        return ResponseEntity.ok(ApiResponse.ok(agendaService.assignAgenda(agendaId, request)));
    }
}
