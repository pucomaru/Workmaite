package com.workmaite.domain.company.repository;

import com.workmaite.domain.company.entity.Company;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface CompanyRepository extends JpaRepository<Company, Integer> {

  Optional<Company> findByName(String name);
}
