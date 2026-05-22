package com.workmaite.domain.organization.dto;

import com.workmaite.domain.organization.entity.MemberRole;
import jakarta.validation.constraints.NotNull;
import lombok.Getter;
import lombok.NoArgsConstructor;

@Getter
@NoArgsConstructor
public class OrganizationMemberUpdateRequest {

    @NotNull(message = "역할은 필수입니다.")
    private MemberRole role;
}
