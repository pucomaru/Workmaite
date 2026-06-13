package com.workmaite.domain.agendas.controller;

import com.workmaite.domain.agendas.dto.*;
import com.workmaite.domain.agendas.service.AgendaService;
import com.workmaite.global.common.ApiResponse;
import jakarta.validation.Valid;
import java.util.List;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

/**
 * 안건 관련 API POST /api/v1/meetings/{meetingId}/agendas/extract - AI 안건 추출 GET
 * /api/v1/meetings/{meetingId}/agendas - 안건 목록 조회 POST /api/v1/meetings/{meetingId}/agendas - 안건 생성
 * GET /api/v1/agendas/{agendaId} - 안건 상세 조회 PATCH /api/v1/agendas/{agendaId} - 안건 수정 DELETE
 * /api/v1/agendas/{agendaId} - 안건 삭제 PATCH /api/v1/agendas/{agendaId}/assignment - 안건 담당자 배정
 */
@RestController
@RequestMapping("/api/v1")
@RequiredArgsConstructor
public class AgendaController {

  private final AgendaService agendaService;

  // AI가 회의체 자료를 분석해 안건을 자동 추출
  @PostMapping("/meetings/{meetingId}/agendas/extract")
  public ResponseEntity<ApiResponse<List<AgendaResponse>>> extractAgendas(
      @PathVariable Long meetingId, @RequestBody @Valid AgendaExtractRequest request) {
    return ResponseEntity.status(HttpStatus.CREATED)
        .body(ApiResponse.ok(agendaService.extractAgendas(meetingId, request)));
  }

  // 회의체의 안건 목록을 orderIndex 오름차순으로 반환
  @GetMapping("/meetings/{meetingId}/agendas")
  public ResponseEntity<ApiResponse<List<AgendaResponse>>> getAgendas(
      @PathVariable Long meetingId) {
    return ResponseEntity.ok(ApiResponse.ok(agendaService.getAgendas(meetingId)));
  }

  // 안건 수동 생성
  @PostMapping("/meetings/{meetingId}/agendas")
  public ResponseEntity<ApiResponse<AgendaResponse>> createAgenda(
      @PathVariable Long meetingId, @RequestBody @Valid AgendaCreateRequest request) {
    return ResponseEntity.status(HttpStatus.CREATED)
        .body(ApiResponse.ok(agendaService.createAgenda(meetingId, request)));
  }

  // 안건 단건 조회
  @GetMapping("/agendas/{agendaId}")
  public ResponseEntity<ApiResponse<AgendaResponse>> getAgenda(@PathVariable Long agendaId) {
    return ResponseEntity.ok(ApiResponse.ok(agendaService.getAgenda(agendaId)));
  }

  // 안건 수정 (title, content, orderIndex, status 부분 수정)
  @PatchMapping("/agendas/{agendaId}")
  public ResponseEntity<ApiResponse<AgendaResponse>> updateAgenda(
      @PathVariable Long agendaId, @RequestBody AgendaUpdateRequest request) {
    return ResponseEntity.ok(ApiResponse.ok(agendaService.updateAgenda(agendaId, request)));
  }

  // 안건 삭제
  @DeleteMapping("/agendas/{agendaId}")
  public ResponseEntity<ApiResponse<Void>> deleteAgenda(@PathVariable Long agendaId) {
    agendaService.deleteAgenda(agendaId);
    return ResponseEntity.ok(ApiResponse.ok(null));
  }

  // 안건 담당자 배정
  @PatchMapping("/agendas/{agendaId}/assignment")
  public ResponseEntity<ApiResponse<AgendaResponse>> assignAgenda(
      @PathVariable Long agendaId, @RequestBody @Valid AgendaAssignmentRequest request) {
    return ResponseEntity.ok(ApiResponse.ok(agendaService.assignAgenda(agendaId, request)));
  }
}
