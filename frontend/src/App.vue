<script setup>
const features = [
  {
    title: '회의체 관리',
    description: '회의체별 담당자, 우선순위, 마감일을 한눈에 관리합니다.',
  },
  {
    title: '자료 업로드',
    description: '회의 자료를 업로드하고 검토 흐름으로 연결합니다.',
  },
  {
    title: 'AI 검토',
    description: 'AI Agent가 회의 자료를 분석해 요약과 검토 초안을 생성합니다.',
  },
  {
    title: 'Action Item 관리',
    description: '회의 이후 해야 할 일을 추적하고 진행 상태를 관리합니다.',
  },
]

const serviceStatus = [
  {
    name: 'Backend API',
    endpoint: '/api/v1/health',
    status: 'UP',
  },
  {
    name: 'AI Agent',
    endpoint: '/health',
    status: 'UP',
  },
]
</script>

<template>
  <main class="page">
    <section class="hero">
      <p class="eyebrow">Workmaite Demo</p>
      <h1>AI 기반 회의 운영 자동화 서비스</h1>
      <p class="description">
        Workmaite는 회의체 관리, 자료 업로드, AI 검토, Action Item 관리를 하나의 흐름으로 연결하는
        업무 지원 서비스입니다.
      </p>
    </section>

    <section class="status-section">
      <h2>서비스 상태</h2>
      <div class="status-grid">
        <article v-for="item in serviceStatus" :key="item.name" class="status-card">
          <div>
            <h3>{{ item.name }}</h3>
            <p>{{ item.endpoint }}</p>
          </div>
          <span class="badge">{{ item.status }}</span>
        </article>
      </div>
    </section>

    <section class="feature-section">
      <h2>주요 기능</h2>
      <div class="feature-grid">
        <article v-for="feature in features" :key="feature.title" class="feature-card">
          <h3>{{ feature.title }}</h3>
          <p>{{ feature.description }}</p>
        </article>
      </div>
    </section>
  </main>
</template>

<style scoped>
.page {
  min-height: 100vh;
  padding: 64px;
  background: #f6f7fb;
  color: #172033;
  font-family:
    Inter, Pretendard, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
}

.hero {
  max-width: 880px;
  padding: 48px;
  border-radius: 28px;
  background: #ffffff;
  box-shadow: 0 20px 60px rgba(15, 23, 42, 0.08);
}

.eyebrow {
  margin: 0 0 16px;
  color: #3763ff;
  font-size: 14px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

h1 {
  margin: 0;
  font-size: 48px;
  line-height: 1.15;
}

.description {
  max-width: 720px;
  margin: 24px 0 0;
  color: #526079;
  font-size: 18px;
  line-height: 1.7;
}

.status-section,
.feature-section {
  margin-top: 36px;
}

h2 {
  margin: 0 0 16px;
  font-size: 24px;
}

.status-grid,
.feature-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 20px;
}

.status-card,
.feature-card {
  padding: 28px;
  border-radius: 24px;
  background: #ffffff;
  box-shadow: 0 12px 40px rgba(15, 23, 42, 0.06);
}

.status-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.status-card h3,
.feature-card h3 {
  margin: 0 0 10px;
  font-size: 20px;
}

.status-card p,
.feature-card p {
  margin: 0;
  color: #647089;
  line-height: 1.6;
}

.badge {
  padding: 8px 14px;
  border-radius: 999px;
  background: #e8f8ef;
  color: #16803c;
  font-size: 14px;
  font-weight: 800;
}

@media (max-width: 768px) {
  .page {
    padding: 28px;
  }

  .hero {
    padding: 32px;
  }

  h1 {
    font-size: 34px;
  }

  .status-grid,
  .feature-grid {
    grid-template-columns: 1fr;
  }
}
</style>
