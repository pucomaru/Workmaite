package com.workmaite.domain.sessions.dto;

import com.fasterxml.jackson.annotation.JsonAlias;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import lombok.Getter;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;

@Getter
@NoArgsConstructor
public class SessionCreateRequest {

    private String title;
    private String description;
    private String location;

    @NotBlank(message = "회의 타입은 필수입니다.")
    private String type;

    @NotNull(message = "예정 일시는 필수입니다.")
    @JsonAlias({"scheduled_at"})
    private LocalDateTime scheduledAt;
}
