package com.workmaite.domain.agendas.controller;

import com.workmaite.domain.agendas.dto.AgendaAssignmentRequest;
import com.workmaite.domain.agendas.dto.AgendaCreateRequest;
import com.workmaite.domain.agendas.dto.AgendaExtractRequest;
import com.workmaite.domain.agendas.dto.AgendaResponse;
import com.workmaite.domain.agendas.dto.AgendaUpdateRequest;
import com.workmaite.domain.agendas.service.AgendaService;
import com.workmaite.global.common.ApiResponse;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import java.util.List;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * 안건 관련 API POST /api/v1/meetings/{meetingId}/agendas/extract - AI 안건 추출 GET
 * /api/v1/meetings/{meetingId}/agendas - 안건 목록 조회 POST /api/v1/meetings/{meetingId}/agendas - 안건 생성
 * GET /api/v1/agendas/{agendaId} - 안건 상세 조회 PATCH /api/v1/agendas/{agendaId} - 안건 수정 DELETE
 * /api/v1/agendas/{agendaId} - 안건 삭제 PATCH /api/v1/agendas/{agendaId}/assignment - 안건 담당자 배정
 */
@Tag(name = "안건", description = "AI 안건 추출, 안건 생성·조회·수정·삭제 및 담당자 배정 API")
@RestController
@RequestMapping("/api/v1")
@RequiredArgsConstructor
public class AgendaController {

  private final AgendaService agendaService;

  @Operation(
      summary = "AI 안건 추출",
      description = "AI가 회의체 자료를 분석해 안건을 자동 추출하고 저장한다. 성공 시 201 Created를 반환한다.")
  @PostMapping("/meetings/{meetingId}/agendas/extract")
  public ResponseEntity<ApiResponse<List<AgendaResponse>>> extractAgendas(
      @PathVariable Long meetingId, @RequestBody @Valid AgendaExtractRequest request) {
    return ResponseEntity.status(HttpStatus.CREATED)
        .body(ApiResponse.ok(agendaService.extractAgendas(meetingId, request)));
  }

  @Operation(summary = "안건 목록 조회", description = "회의체의 안건 목록을 orderIndex 오름차순으로 반환한다.")
  @GetMapping("/meetings/{meetingId}/agendas")
  public ResponseEntity<ApiResponse<List<AgendaResponse>>> getAgendas(
      @PathVariable Long meetingId) {
    return ResponseEntity.ok(ApiResponse.ok(agendaService.getAgendas(meetingId)));
  }

  @Operation(summary = "안건 생성", description = "회의체에 안건을 수동으로 생성한다. 성공 시 201 Created를 반환한다.")
  @PostMapping("/meetings/{meetingId}/agendas")
  public ResponseEntity<ApiResponse<AgendaResponse>> createAgenda(
      @PathVariable Long meetingId, @RequestBody @Valid AgendaCreateRequest request) {
    return ResponseEntity.status(HttpStatus.CREATED)
        .body(ApiResponse.ok(agendaService.createAgenda(meetingId, request)));
  }

  @Operation(summary = "안건 상세 조회", description = "특정 안건의 상세 정보를 단건 조회한다.")
  @GetMapping("/agendas/{agendaId}")
  public ResponseEntity<ApiResponse<AgendaResponse>> getAgenda(@PathVariable Long agendaId) {
    return ResponseEntity.ok(ApiResponse.ok(agendaService.getAgenda(agendaId)));
  }

  @Operation(summary = "안건 수정", description = "안건의 title·content·orderIndex·status를 부분 수정한다.")
  @PatchMapping("/agendas/{agendaId}")
  public ResponseEntity<ApiResponse<AgendaResponse>> updateAgenda(
      @PathVariable Long agendaId, @RequestBody AgendaUpdateRequest request) {
    return ResponseEntity.ok(ApiResponse.ok(agendaService.updateAgenda(agendaId, request)));
  }

  @Operation(summary = "안건 삭제", description = "특정 안건을 삭제한다.")
  @DeleteMapping("/agendas/{agendaId}")
  public ResponseEntity<ApiResponse<Void>> deleteAgenda(@PathVariable Long agendaId) {
    agendaService.deleteAgenda(agendaId);
    return ResponseEntity.ok(ApiResponse.ok(null));
  }

  @Operation(summary = "안건 담당자 배정", description = "특정 안건에 담당자를 배정한다.")
  @PatchMapping("/agendas/{agendaId}/assignment")
  public ResponseEntity<ApiResponse<AgendaResponse>> assignAgenda(
      @PathVariable Long agendaId, @RequestBody @Valid AgendaAssignmentRequest request) {
    return ResponseEntity.ok(ApiResponse.ok(agendaService.assignAgenda(agendaId, request)));
  }
}
