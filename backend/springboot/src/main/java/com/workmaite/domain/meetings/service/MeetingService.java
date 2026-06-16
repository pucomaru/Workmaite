package com.workmaite.domain.meetings.service;

import com.workmaite.domain.meetings.dto.ActiveMeetingResponse;
import com.workmaite.domain.meetings.dto.MeetingCreateRequest;
import com.workmaite.domain.meetings.dto.MeetingDetailResponse;
import com.workmaite.domain.meetings.dto.MeetingMemberAddRequest;
import com.workmaite.domain.meetings.dto.MeetingMemberResponse;
import com.workmaite.domain.meetings.dto.MeetingMemberUpdateRequest;
import com.workmaite.domain.meetings.dto.MeetingResponse;
import com.workmaite.domain.meetings.dto.MeetingUpdateRequest;
import com.workmaite.domain.meetings.entity.Meeting;
import com.workmaite.domain.meetings.entity.MeetingMember;
import com.workmaite.domain.meetings.entity.MeetingMemberRole;
import com.workmaite.domain.meetings.entity.MeetingStatus;
import com.workmaite.domain.meetings.repository.MeetingMemberRepository;
import com.workmaite.domain.meetings.repository.MeetingRepository;
import com.workmaite.domain.agendas.repository.AgendaRepository;
import com.workmaite.domain.chat.repository.ChatMessageRepository;
import com.workmaite.domain.logs.repository.AgentLogRepository;
import com.workmaite.domain.logs.repository.HitlReviewRepository;
import com.workmaite.domain.reports.repository.ReportRepository;
import com.workmaite.domain.reports.repository.ReportScoreRepository;
import com.workmaite.domain.sessions.repository.SessionRepository;
import com.workmaite.domain.sessions.service.SessionService;
import com.workmaite.domain.user.entity.User;
import com.workmaite.domain.user.entity.UserRole;
import com.workmaite.domain.user.repository.UserRepository;
import com.workmaite.global.audit.AuditLogged;
import com.workmaite.global.auth.MeetingAccessGuard;
import com.workmaite.global.exception.BusinessException;
import com.workmaite.global.exception.ErrorCode;
import com.workmaite.global.sync.NeoSyncService;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;
import lombok.RequiredArgsConstructor;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Lazy;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 회의체 비즈니스 로직 - 생성: 생성자를 간사로 자동 등록 - 내 진행중인 회의체: 로그인 유저가 속한 active 회의체 + 담당 간사명 조합 - 목록/검색:
 * keyword가 있으면 제목·목적 필드에서 검색, 없으면 전체 반환 - 상세 조회: 참여자 목록을 함께 반환 - 수정·참여자 관리: 요청자가 해당 회의체의
 * secretary인지 확인 후 처리
 */
@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class MeetingService {

  private final MeetingRepository meetingRepository;
  private final MeetingMemberRepository meetingMemberRepository;
  private final UserRepository userRepository;
  private final NeoSyncService neoSyncService;
  private final MeetingAccessGuard meetingAccessGuard;
  // SessionService ↔ MeetingService 순환 참조 차단 — @Lazy 필드 주입(생성자에서 제외).
  @Autowired @Lazy private SessionService sessionService;
  private final SessionRepository sessionRepository;
  private final AgendaRepository agendaRepository;
  private final ReportRepository reportRepository;
  private final ReportScoreRepository reportScoreRepository;
  private final HitlReviewRepository hitlReviewRepository;
  private final ChatMessageRepository chatMessageRepository;
  private final AgentLogRepository agentLogRepository;

  /**
   * 회의체 삭제 — PostgreSQL이 원천. 세션은 검증된 단일 삭제 로직을 재사용하고, 회의체 직속 자식을 FK-안전 순서로 정리한 뒤
   * 회의체를 지우고 Neo4j 삭제를 아웃박스로 전파한다. 로그(agent_logs·token_usage)와 대화(chat)는 보존(링크만 해제).
   */
  @Transactional
  @AuditLogged(action = "DELETE", entityType = "meeting")
  public void deleteMeeting(Long meetingId) {
    Meeting meeting =
        meetingRepository
            .findById(meetingId)
            .orElseThrow(() -> new BusinessException(ErrorCode.MEETING_NOT_FOUND));
    meetingAccessGuard.requireMeetingEdit(meetingId);

    // 1) 세션: 검증된 단일 삭제 로직 재사용(세션 자식 정리·로그 보존·Neo4j 동기화 포함)
    sessionRepository
        .findByMeetingId(meetingId)
        .forEach(s -> sessionService.deleteSession(s.getId()));

    // 2) 회의체 직속 자식 정리 — FK 안전 순서. 로그·토큰사용량은 보존.
    hitlReviewRepository.deleteByMeetingAgendas(meetingId);
    hitlReviewRepository.deleteByMeetingReports(meetingId);
    reportScoreRepository.deleteByMeetingId(meetingId);
    reportRepository.deleteByMeetingId(meetingId);
    agendaRepository.deleteByMeetingId(meetingId);
    meetingMemberRepository.deleteByMeetingId(meetingId);
    chatMessageRepository.detachMeeting(meetingId); // 대화 보존, 링크만 해제
    agentLogRepository.detachMeeting(meetingId); // 로그 보존, 링크만 해제

    // 3) 보류된 세션 삭제를 먼저 DB에 반영(FK 안전) 후 회의체 삭제 + Neo4j 동기화(아웃박스)
    meetingRepository.flush();
    meetingRepository.delete(meeting);
    neoSyncService.deleteMeeting(meetingId);
  }

  @Transactional
  @AuditLogged(action = "CREATE", entityType = "meeting")
  public MeetingResponse createMeeting(Long requesterId, MeetingCreateRequest request) {
    Meeting meeting =
        Meeting.create(
            request.getTitle(),
            request.getDescription(),
            request.getGuidelines(),
            request.getType(),
            request.getStartDateTime(),
            request.getEndDateTime(),
            requesterId);
    Meeting saved = meetingRepository.save(meeting);
    MeetingMember admin = MeetingMember.create(saved.getId(), requesterId, MeetingMemberRole.ADMIN);
    meetingMemberRepository.save(admin);
    neoSyncService.syncMeeting(saved.getId());
    return MeetingResponse.from(saved);
  }

  private static final int MAX_PAGE_SIZE = 100;

  /**
   * 회의체 목록/검색 (P8-4). 조회 스코프는 company_role 기준: SYSTEM_ADMIN=전체, COMPANY_ADMIN=자사가 참여한 회의체, USER=내가
   * 멤버인 회의체. size 미지정 시 기존 전체 반환(호환 모드).
   */
  public List<MeetingResponse> getMeetings(
      Long userId, String keyword, Integer page, Integer size) {
    User caller =
        userRepository
            .findById(userId)
            .orElseThrow(() -> new BusinessException(ErrorCode.USER_NOT_FOUND));

    // 1) 역할별 가시 회의체
    List<Meeting> visible = getVisibleMeetings(caller);

    // 2) 키워드 필터 (제목·설명)
    if (keyword != null && !keyword.isBlank()) {
      String kw = keyword.toLowerCase();
      visible =
          visible.stream()
              .filter(
                  m ->
                      (m.getTitle() != null && m.getTitle().toLowerCase().contains(kw))
                          || (m.getDescription() != null
                              && m.getDescription().toLowerCase().contains(kw)))
              .toList();
    }

    // 3) 최신순 정렬 + 페이지네이션 (size 미지정 시 전체)
    visible =
        visible.stream()
            .sorted(
                Comparator.comparing(
                    Meeting::getCreatedAt, Comparator.nullsLast(Comparator.reverseOrder())))
            .toList();
    if (size != null) {
      int s = Math.min(Math.max(size, 1), MAX_PAGE_SIZE);
      int from = Math.min(Math.max(page == null ? 0 : page, 0) * s, visible.size());
      visible = visible.subList(from, Math.min(from + s, visible.size()));
    }

    // 4) 내 회의체 권한(my_role) 매핑 — 멤버가 아닌(회사관리자/시스템관리자) 회의체는 null
    Map<Long, String> roleMap =
        meetingMemberRepository.findByUserId(userId).stream()
            .collect(
                Collectors.toMap(
                    MeetingMember::getMeetingId,
                    mm -> mm.getMeetingRole() == MeetingMemberRole.ADMIN ? "admin" : "member",
                    (a, b) -> a));
    return visible.stream().map(m -> MeetingResponse.from(m, roleMap.get(m.getId()))).toList();
  }

  // company_role 기준 가시 회의체. getMeetings/getMyActiveMeetings가 동일 스코프를 공유한다.
  public List<Meeting> getVisibleMeetings(User caller) {
    if (caller.getCompanyRole() == UserRole.SYSTEM_ADMIN) {
      return meetingRepository.findAll();
    } else if (caller.getCompanyRole() == UserRole.COMPANY_ADMIN && caller.getCompanyId() != null) {
      return meetingRepository.findByParticipatingCompany(caller.getCompanyId());
    }
    return meetingRepository.findByUserId(caller.getId());
  }

  // secretary가 여러 명일 경우 첫 번째만 담당자로 사용. 홈 "진행 중 회의체" 테이블의 단일 데이터 소스로,
  // 조회 스코프를 getMeetings와 동일하게 맞춰 간사·참여자·역할이 항상 같은 회의체 집합에 대해 채워지도록 한다.
  public List<ActiveMeetingResponse> getMyActiveMeetings(Long userId) {
    User caller =
        userRepository
            .findById(userId)
            .orElseThrow(() -> new BusinessException(ErrorCode.USER_NOT_FOUND));
    List<Meeting> meetings =
        getVisibleMeetings(caller).stream()
            .filter(m -> m.getStatus() == MeetingStatus.ACTIVE)
            .toList();
    if (meetings.isEmpty()) return List.of();

    List<Long> meetingIds = meetings.stream().map(Meeting::getId).toList();
    List<MeetingMember> admins =
        meetingMemberRepository.findByMeetingIdInAndMeetingRole(
            meetingIds, MeetingMemberRole.ADMIN);

    List<Long> adminUserIds = admins.stream().map(MeetingMember::getUserId).distinct().toList();
    Map<Long, String> userNameMap =
        userRepository.findAllById(adminUserIds).stream()
            .collect(Collectors.toMap(User::getId, User::getName));

    Map<Long, String> adminNameMap =
        admins.stream()
            .collect(
                Collectors.toMap(
                    MeetingMember::getMeetingId,
                    m -> userNameMap.getOrDefault(m.getUserId(), ""),
                    (first, second) -> first));

    List<MeetingMember> allMembers = meetingMemberRepository.findByMeetingIdIn(meetingIds);
    Map<Long, Long> memberCountMap =
        allMembers.stream()
            .collect(Collectors.groupingBy(MeetingMember::getMeetingId, Collectors.counting()));

    // 내 회의체 권한(my_role) — 멤버가 아닌(회사관리자/시스템관리자) 회의체는 null
    Map<Long, String> myRoleMap =
        meetingMemberRepository.findByUserId(userId).stream()
            .collect(
                Collectors.toMap(
                    MeetingMember::getMeetingId,
                    mm -> mm.getMeetingRole() == MeetingMemberRole.ADMIN ? "admin" : "member",
                    (a, b) -> a));

    return meetings.stream()
        .map(
            m ->
                ActiveMeetingResponse.from(
                    m,
                    adminNameMap.get(m.getId()),
                    memberCountMap.getOrDefault(m.getId(), 0L).intValue(),
                    myRoleMap.get(m.getId())))
        .toList();
  }

  public MeetingDetailResponse getMeeting(Long meetingId) {
    meetingAccessGuard.requireView(meetingId);
    Meeting meeting = findMeetingOrThrow(meetingId);
    List<MeetingMember> members = meetingMemberRepository.findByMeetingId(meetingId);
    Map<Long, User> userMap = buildUserMap(members);
    return MeetingDetailResponse.from(meeting, members, userMap);
  }

  public List<MeetingMemberResponse> findMembers(Long meetingId) {
    meetingAccessGuard.requireView(meetingId);
    List<MeetingMember> members = meetingMemberRepository.findByMeetingId(meetingId);
    Map<Long, User> userMap = buildUserMap(members);
    return members.stream()
        .map(mm -> MeetingMemberResponse.from(mm, userMap.get(mm.getUserId())))
        .toList();
  }

  @Transactional
  @AuditLogged(action = "UPDATE", entityType = "meeting")
  public MeetingResponse updateMeeting(
      Long meetingId, Long requesterId, MeetingUpdateRequest request) {
    checkSecretaryPermission(meetingId, requesterId);
    Meeting meeting = findMeetingOrThrow(meetingId);
    meeting.update(
        request.getTitle(),
        request.getDescription(),
        request.getGuidelines(),
        request.getType(),
        request.getStartDateTime(),
        request.getEndDateTime(),
        request.getStatus());
    neoSyncService.syncMeeting(meetingId);
    return MeetingResponse.from(meeting);
  }

  @Transactional
  @AuditLogged(action = "ADD", entityType = "member")
  public MeetingMemberResponse addMember(
      Long meetingId, Long requesterId, MeetingMemberAddRequest request) {
    checkSecretaryPermission(meetingId, requesterId);
    findMeetingOrThrow(meetingId);
    if (meetingMemberRepository.existsByMeetingIdAndUserId(meetingId, request.getUserId())) {
      throw new BusinessException(ErrorCode.MEETING_MEMBER_ALREADY_EXISTS);
    }
    MeetingMember member =
        MeetingMember.create(meetingId, request.getUserId(), request.getMeetingRole());
    MeetingMember saved = meetingMemberRepository.save(member);
    User user = userRepository.findById(saved.getUserId()).orElse(null);
    String roleStr = (request.getMeetingRole() == MeetingMemberRole.ADMIN) ? "admin" : "member";
    neoSyncService.syncMember(meetingId, request.getUserId(), roleStr);
    return MeetingMemberResponse.from(saved, user);
  }

  @Transactional
  @AuditLogged(action = "REMOVE", entityType = "member")
  public void removeMember(Long meetingId, Long requesterId, Long memberId) {
    checkSecretaryPermission(meetingId, requesterId);
    MeetingMember member =
        meetingMemberRepository
            .findById(memberId)
            .orElseThrow(() -> new BusinessException(ErrorCode.MEETING_MEMBER_NOT_FOUND));
    Long userId = member.getUserId();
    meetingMemberRepository.delete(member);
    neoSyncService.deleteMember(meetingId, userId);
  }

  @Transactional
  @AuditLogged(action = "UPDATE", entityType = "member")
  public MeetingMemberResponse updateMemberRole(
      Long meetingId, Long requesterId, Long memberId, MeetingMemberUpdateRequest request) {
    checkSecretaryPermission(meetingId, requesterId);
    MeetingMember member =
        meetingMemberRepository
            .findById(memberId)
            .orElseThrow(() -> new BusinessException(ErrorCode.MEETING_MEMBER_NOT_FOUND));
    member.updateMeetingRole(request.getMeetingRole());
    User user = userRepository.findById(member.getUserId()).orElse(null);
    String roleStr = (request.getMeetingRole() == MeetingMemberRole.ADMIN) ? "admin" : "member";
    neoSyncService.syncMember(meetingId, member.getUserId(), roleStr);
    return MeetingMemberResponse.from(member, user);
  }

  /** 현재 사용자의 특정 회의체 내 권한 반환 (없으면 null) */
  public String getMyMeetingRole(Long meetingId, Long userId) {
    return meetingMemberRepository
        .findByMeetingIdAndUserId(meetingId, userId)
        .map(m -> m.getMeetingRole() == MeetingMemberRole.ADMIN ? "admin" : "member")
        .orElse(null);
  }

  private Meeting findMeetingOrThrow(Long meetingId) {
    return meetingRepository
        .findById(meetingId)
        .orElseThrow(() -> new BusinessException(ErrorCode.MEETING_NOT_FOUND));
  }

  private Map<Long, User> buildUserMap(List<MeetingMember> members) {
    List<Long> userIds = members.stream().map(MeetingMember::getUserId).distinct().toList();
    return userRepository.findAllById(userIds).stream()
        .collect(Collectors.toMap(User::getId, u -> u));
  }

  // 회의체 운영 권한 검증: 간사 | 회사관리자(자사 소유 회의체) | 시스템관리자 (requireMeetingEdit에 위임)
  private void checkSecretaryPermission(Long meetingId, Long requesterId) {
    meetingAccessGuard.requireMeetingEdit(meetingId);
  }
}
