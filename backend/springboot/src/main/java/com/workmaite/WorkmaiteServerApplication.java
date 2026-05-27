package com.workmaite;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.data.jpa.repository.config.EnableJpaAuditing;

@EnableJpaAuditing
@SpringBootApplication
public class WorkmaiteServerApplication {

	public static void main(String[] args) {
		SpringApplication.run(WorkmaiteServerApplication.class, args);
	}

}
