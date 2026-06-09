<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'

const props = defineProps({
  displayName: { type: String, default: '참여자' },
})

const emit = defineEmits(['join', 'cancel'])

const micOn = ref(true)
const camOn = ref(true)

// 로컬 스트림 미리보기
const previewRef = ref(null)
let localStream = null

async function startPreview() {
  try {
    localStream = await navigator.mediaDevices.getUserMedia({
      video: camOn.value,
      audio: false, // 미리보기용 — 오디오 출력 불필요
    })
    if (previewRef.value) {
      previewRef.value.srcObject = localStream
    }
  } catch (e) {
    // 카메라 권한 거부 시 camOn 강제 off
    camOn.value = false
  }
}

function stopPreview() {
  if (localStream) {
    localStream.getTracks().forEach(t => t.stop())
    localStream = null
  }
}

async function toggleCamPreview() {
  camOn.value = !camOn.value
  if (camOn.value) {
    await startPreview()
  } else {
    stopPreview()
    if (previewRef.value) previewRef.value.srcObject = null
  }
}

function handleJoin() {
  stopPreview()
  emit('join', { micOn: micOn.value, camOn: camOn.value })
}

function handleCancel() {
  stopPreview()
  emit('cancel')
}

onMounted(() => {
  startPreview()
})

onBeforeUnmount(() => {
  stopPreview()
})
</script>

<template>
  <div class="lobby-overlay">
    <div class="lobby-card">
      <h2 class="lobby-title">회의 입장 전 설정</h2>

      <!-- 카메라 미리보기 -->
      <div class="lobby-preview-wrap">
        <video
          v-show="camOn"
          ref="previewRef"
          autoplay
          playsinline
          muted
          class="lobby-preview"
        />
        <div v-if="!camOn" class="lobby-preview lobby-preview--off">
          <span class="cam-off-icon">📷</span>
          <p>카메라 꺼짐</p>
        </div>
        <div class="lobby-name-badge">{{ displayName }}</div>
      </div>

      <!-- 장치 토글 -->
      <div class="lobby-controls">
        <button
          class="lobby-ctrl-btn"
          :class="{ 'ctrl-off': !micOn }"
          @click="micOn = !micOn"
          :title="micOn ? '마이크 끄기' : '마이크 켜기'"
        >
          <span class="ctrl-icon">{{ micOn ? '🎙️' : '🔇' }}</span>
          <span class="ctrl-label">{{ micOn ? '마이크 켜짐' : '마이크 꺼짐' }}</span>
        </button>

        <button
          class="lobby-ctrl-btn"
          :class="{ 'ctrl-off': !camOn }"
          @click="toggleCamPreview"
          :title="camOn ? '카메라 끄기' : '카메라 켜기'"
        >
          <span class="ctrl-icon">{{ camOn ? '📹' : '📷' }}</span>
          <span class="ctrl-label">{{ camOn ? '카메라 켜짐' : '카메라 꺼짐' }}</span>
        </button>
      </div>

      <!-- 입장 / 취소 -->
      <div class="lobby-actions">
        <button class="btn-cancel" @click="handleCancel">취소</button>
        <button class="btn-join" @click="handleJoin">입장하기</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.lobby-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.75);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.lobby-card {
  background: var(--dark-card);
  border-radius: 16px;
  padding: 32px;
  width: 420px;
  display: flex;
  flex-direction: column;
  gap: 20px;
  color: var(--surface-2);
}

.lobby-title {
  font-size: 20px;
  font-weight: 700;
  text-align: center;
  margin: 0;
}

/* 미리보기 */
.lobby-preview-wrap {
  position: relative;
  border-radius: 12px;
  overflow: hidden;
  background: var(--dark-bg);
  aspect-ratio: 16/9;
}

.lobby-preview {
  width: 100%;
  height: 100%;
  object-fit: cover;
  transform: scaleX(-1); /* 거울 모드 */
}

.lobby-preview--off {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  color: var(--dark-muted);
  font-size: 14px;
}

.cam-off-icon {
  font-size: 40px;
}

.lobby-name-badge {
  position: absolute;
  bottom: 10px;
  left: 12px;
  background: rgba(0, 0, 0, 0.55);
  color: #fff;
  font-size: 13px;
  padding: 3px 10px;
  border-radius: 20px;
  backdrop-filter: blur(4px);
}

/* 장치 토글 버튼 */
.lobby-controls {
  display: flex;
  gap: 12px;
  justify-content: center;
}

.lobby-ctrl-btn {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  background: var(--dark-border);
  border: none;
  border-radius: 12px;
  padding: 12px 20px;
  cursor: pointer;
  color: var(--surface-2);
  flex: 1;
}

.lobby-ctrl-btn:hover {
  background: var(--text-dim);
}

.lobby-ctrl-btn.ctrl-off {
  background: #7f1d1d;
}

.lobby-ctrl-btn.ctrl-off:hover {
  background: #991b1b;
}

.ctrl-icon {
  font-size: 24px;
}

.ctrl-label {
  font-size: 12px;
  color: #cbd5e1;
}

/* 입장/취소 */
.lobby-actions {
  display: flex;
  gap: 12px;
}

.btn-cancel {
  flex: 1;
  padding: 12px;
  border-radius: 10px;
  border: 1px solid var(--text-dim);
  background: transparent;
  color: var(--dark-muted);
  cursor: pointer;
  font-size: 15px;
}

.btn-cancel:hover {
  background: var(--dark-border);
}

.btn-join {
  flex: 2;
  padding: 12px;
  border-radius: 10px;
  border: none;
  background: var(--accent);
  color: #fff;
  cursor: pointer;
  font-size: 15px;
  font-weight: 600;
}

.btn-join:hover {
  background: #2563eb;
}
</style>
