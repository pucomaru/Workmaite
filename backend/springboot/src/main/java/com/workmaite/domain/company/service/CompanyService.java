package com.workmaite.domain.company.service;

import com.workmaite.domain.company.entity.Company;
import com.workmaite.domain.company.repository.CompanyRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@RequiredArgsConstructor
public class CompanyService {

    private final CompanyRepository companyRepository;

    /** 회사명으로 조회, 없으면 생성 (P1-7② — 자유 텍스트를 정규화 엔티티로 흡수). */
    @Transactional
    public Company getOrCreate(String name) {
        if (name == null || name.isBlank()) {
            return null;
        }
        String trimmed = name.trim();
        return companyRepository.findByName(trimmed)
                .orElseGet(() -> companyRepository.save(Company.builder().name(trimmed).build()));
    }
}
