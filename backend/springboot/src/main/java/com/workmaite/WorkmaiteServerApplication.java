package com.workmaite;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.data.jpa.repository.config.EnableJpaAuditing;
import org.springframework.scheduling.annotation.EnableScheduling;

@EnableJpaAuditing
@EnableScheduling // 아웃박스 폴러 (P2-4)
@SpringBootApplication
public class WorkmaiteServerApplication {

  public static void main(String[] args) {
    SpringApplication.run(WorkmaiteServerApplication.class, args);
  }
}
