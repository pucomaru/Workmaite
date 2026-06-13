import js from '@eslint/js'
import pluginVue from 'eslint-plugin-vue'
import globals from 'globals'
import prettier from 'eslint-config-prettier'

// 기존 코드베이스에 점진 적용하기 위해 차단 규칙은 최소화하고 warn 위주로 시작한다.
// (frontend/PLAN.md Phase 0 — 강화는 단계적으로)
export default [
  { ignores: ['dist/**', 'node_modules/**', 'scripts/**'] },
  js.configs.recommended,
  ...pluginVue.configs['flat/essential'],
  {
    languageOptions: {
      ecmaVersion: 'latest',
      globals: { ...globals.browser },
    },
    rules: {
      'no-unused-vars': ['warn', { argsIgnorePattern: '^_', varsIgnorePattern: '^_' }],
      'no-empty': ['warn', { allowEmptyCatch: true }], // 의도적 폴백 catch 허용 (Phase 2에서 재분류)
      'no-useless-assignment': 'warn',
      'vue/multi-word-component-names': 'off', // 기존 페이지 명명 관례 유지
      // 기존 편집 모달들이 prop 객체를 직접 변형하는 패턴 — Phase 3 모달 재설계에서 해소 예정
      'vue/no-mutating-props': 'warn',
    },
  },
  // Prettier와 충돌하는 포맷 규칙 비활성화 (반드시 마지막) — 포맷은 prettier가 전담
  prettier,
]
