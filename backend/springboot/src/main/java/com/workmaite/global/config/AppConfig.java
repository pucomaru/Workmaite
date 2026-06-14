package com.workmaite.global.config;

import java.time.Duration;
import org.springframework.boot.restclient.RestTemplateBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.web.client.RestTemplate;

@Configuration
@EnableAsync
public class AppConfig {

  @Bean
  public RestTemplate restTemplate(RestTemplateBuilder builder) {
    return builder.connectTimeout(Duration.ofSeconds(3)).readTimeout(Duration.ofSeconds(5)).build();
  }
}
