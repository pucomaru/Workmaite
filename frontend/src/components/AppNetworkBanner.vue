<template>
  <Transition name="netbanner">
    <div v-if="networkDown" class="net-banner" role="alert">
      <i class="bi bi-wifi-off"></i>
      서버에 연결할 수 없습니다 — 표시 중인 데이터는 최신이 아닐 수 있습니다.
    </div>
  </Transition>
</template>

<script setup>
import { networkDown } from '../stores/network'
</script>

<style scoped>
.net-banner {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  z-index: 3100;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  background: var(--danger);
  color: #fff;
  font-size: 12.5px;
  font-weight: 600;
  padding: 7px 16px;
}
.netbanner-enter-active,
.netbanner-leave-active {
  transition:
    transform 0.2s,
    opacity 0.2s;
}
.netbanner-enter-from,
.netbanner-leave-to {
  transform: translateY(-100%);
  opacity: 0;
}
</style>
