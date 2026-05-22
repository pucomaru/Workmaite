<script setup>
import { ref, onMounted, onBeforeUnmount, watch } from 'vue'
import {
  Room,
  RoomEvent,
  Track,
  createLocalTracks,
  VideoPresets,
  ParticipantEvent,
} from 'livekit-client'
import { useSTT } from '../composables/useSTT.js'

const props = defineProps({
  token: { type: String, required: true },
  url: { type: String, required: true },
  displayName: { type: String, default: '참여자' },
  initialMic: { type: Boolean, default: true },
  initialCam: { type: Boolean, default: true },
})

const emit = defineEmits(['participantCountChange', 'transcript'])

// ─── State ───────────────────────────────────────────────────────────────────
const room = ref(null)
const participants = ref([])   // { sid, identity, name, videoTrack, audioEnabled, videoEnabled, isSelf }
const micOn = ref(props.initialMic)
const camOn = ref(props.initialCam)
const isConnected = ref(false)
const isConnecting = ref(true)
const error = ref(null)

// DOM refs for local tracks
const localVideoRef = ref(null)

// ─── STT ─────────────────────────────────────────────────────────────────────
const encoder = new TextEncoder()
const decoder = new TextDecoder()

function publishTranscript(text) {
  if (!room.value) return
  const now = new Date().toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  const payload = encoder.encode(JSON.stringify({
    type: 'transcript',
    name: props.displayName,
    text,
    time: now,
  }))
  room.value.localParticipant.publishData(payload, { reliable: true })
  // 본인 발화도 즉시 emit (isSelf: true)
  emit('transcript', { name: props.displayName, text, time: now, isSelf: true })
}

const stt = useSTT({ onResult: publishTranscript })

// ─── Helpers ─────────────────────────────────────────────────────────────────
function buildParticipantEntry(p, isSelf = false) {
  const videoPublication = [...p.trackPublications.values()].find(
    pub => pub.kind === Track.Kind.Video && pub.track,
  )
  const audioPublication = [...p.trackPublications.values()].find(
    pub => pub.kind === Track.Kind.Audio && pub.track,
  )
  return {
    sid: p.sid,
    identity: p.identity,
    name: p.name || p.identity,
    videoTrack: videoPublication?.track ?? null,
    audioEnabled: audioPublication ? !p.isMicrophoneMuted : false,
    videoEnabled: videoPublication ? !p.isCameraOff : false,
    isSelf,
  }
}

function refreshParticipants(r) {
  const list = []
  // local
  list.push(buildParticipantEntry(r.localParticipant, true))
  // remote
  for (const rp of r.remoteParticipants.values()) {
    list.push(buildParticipantEntry(rp, false))
  }
  participants.value = list
  emit('participantCountChange', list.length)
}

// Attach a video track to a <video> element by participant sid
function attachVideo(sid, el) {
  const entry = participants.value.find(p => p.sid === sid)
  if (entry?.videoTrack && el) {
    entry.videoTrack.attach(el)
  }
}

// ─── Connect ─────────────────────────────────────────────────────────────────
onMounted(async () => {
  try {
    // 상대경로인 경우 현재 호스트 기준으로 ws:// URL 생성
    let connectUrl = props.url
    if (connectUrl.startsWith('/')) {
      const proto = location.protocol === 'https:' ? 'wss' : 'ws'
      connectUrl = `${proto}://${location.host}${connectUrl}`
    }

    const r = new Room({
      adaptiveStream: true,
      dynacast: true,
      videoCaptureDefaults: { resolution: VideoPresets.h360.resolution },
    })
    room.value = r

    // ── Room event handlers ──────────────────────────────────────────────────
    r.on(RoomEvent.TrackSubscribed, (track, pub, participant) => {
      refreshParticipants(r)
    })
    r.on(RoomEvent.TrackUnsubscribed, () => refreshParticipants(r))
    r.on(RoomEvent.ParticipantConnected, () => refreshParticipants(r))
    r.on(RoomEvent.ParticipantDisconnected, () => refreshParticipants(r))
    r.on(RoomEvent.TrackMuted, () => refreshParticipants(r))
    r.on(RoomEvent.TrackUnmuted, () => refreshParticipants(r))
    r.on(RoomEvent.LocalTrackPublished, () => refreshParticipants(r))
    r.on(RoomEvent.Disconnected, () => {
      isConnected.value = false
      stt.stop()
    })

    // ── 원격 참여자 자막 수신 ──────────────────────────────────────────────────
    r.on(RoomEvent.DataReceived, (payload) => {
      try {
        const msg = JSON.parse(decoder.decode(payload))
        if (msg.type === 'transcript') {
          emit('transcript', { name: msg.name, text: msg.text, time: msg.time, isSelf: false })
        }
      } catch (_) {}
    })

    await r.connect(connectUrl, props.token, { autoSubscribe: true })

    // publish local tracks (로비에서 선택한 초기 상태 적용)
    const tracks = await createLocalTracks({
      audio: props.initialMic,
      video: props.initialCam,
    })
    for (const t of tracks) {
      await r.localParticipant.publishTrack(t)
    }

    isConnected.value = true
    isConnecting.value = false
    refreshParticipants(r)
    // 마이크가 켜진 경우 STT 시작
    if (props.initialMic) stt.start()
  } catch (e) {
    error.value = e.message || 'LiveKit 연결 실패'
    isConnecting.value = false
    console.error('[LiveKit]', e)
  }
})

onBeforeUnmount(async () => {
  stt.stop()
  if (room.value) {
    await room.value.disconnect()
  }
})

// ─── Controls ────────────────────────────────────────────────────────────────
async function toggleMic() {
  if (!room.value) return
  micOn.value = !micOn.value
  await room.value.localParticipant.setMicrophoneEnabled(micOn.value)
  micOn.value ? stt.start() : stt.stop()
}

async function toggleCam() {
  if (!room.value) return
  camOn.value = !camOn.value
  await room.value.localParticipant.setCameraEnabled(camOn.value)
}

async function leaveRoom() {
  if (room.value) await room.value.disconnect()
}

defineExpose({ micOn, camOn, isConnecting, error, toggleMic, toggleCam, leaveRoom })
</script>

<template>
  <div class="lk-inline">
    <!-- 연결 중 -->
    <div v-if="isConnecting" class="lk-status">
      <div class="lk-spinner"></div>
      <p>회의실 연결 중...</p>
    </div>

    <!-- 오류 -->
    <div v-else-if="error" class="lk-status lk-error">
      <p>⚠ {{ error }}</p>
      <p style="font-size:12px;color:#94a3b8;margin-top:8px">
        LiveKit 서버가 실행 중인지 확인하세요.
      </p>
    </div>

    <!-- 비디오 그리드 -->
    <div v-else class="lk-grid">
      <div
        v-for="p in participants"
        :key="p.sid"
        class="lk-tile"
      >
        <video
          v-if="p.videoEnabled && p.videoTrack"
          autoplay
          playsinline
          muted
          class="lk-video"
          :ref="el => { if (el) attachVideo(p.sid, el) }"
        />
        <div v-else class="lk-avatar">
          {{ (p.name || '?')[0].toUpperCase() }}
        </div>
        <div class="lk-name-tag">
          <span>{{ p.isSelf ? `${p.name} (나)` : p.name }}</span>
          <span v-if="!p.audioEnabled" class="lk-muted-icon">🔇</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.lk-inline {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  background: #0f172a;
}

.lk-status {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: #94a3b8;
  gap: 16px;
}
.lk-error { color: #fca5a5; }

.lk-spinner {
  width: 36px;
  height: 36px;
  border: 3px solid #334155;
  border-top-color: #3b82f6;
  border-radius: 50%;
  animation: spin .8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

.lk-grid {
  flex: 1;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 8px;
  padding: 16px;
  overflow-y: auto;
  align-content: start;
}

.lk-tile {
  position: relative;
  background: #1e293b;
  border-radius: 10px;
  aspect-ratio: 16/9;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
}

.lk-video {
  width: 100%;
  height: 100%;
  object-fit: cover;
  transform: scaleX(-1);
}

.lk-avatar {
  width: 64px;
  height: 64px;
  background: #1d4ed8;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 28px;
  font-weight: 700;
  color: #fff;
}

.lk-name-tag {
  position: absolute;
  bottom: 8px;
  left: 8px;
  background: rgba(0,0,0,.6);
  color: #e2e8f0;
  font-size: 12px;
  padding: 3px 8px;
  border-radius: 6px;
  display: flex;
  align-items: center;
  gap: 6px;
}
.lk-muted-icon { font-size: 11px; }
</style>

<style scoped>
.lk-popup-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, .75);
  z-index: 9999;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
}

.lk-popup {
  width: min(1000px, 100%);
  max-height: calc(100vh - 48px);
  background: #0f172a;
  border-radius: 16px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  box-shadow: 0 24px 80px rgba(0,0,0,.6);
}

.lk-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 20px;
  background: #1e293b;
  border-bottom: 1px solid #334155;
  flex-shrink: 0;
}

.lk-title { font-weight: 700; font-size: 15px; color: #e2e8f0; }

.lk-badge {
  background: #1d4ed8;
  color: #fff;
  font-size: 12px;
  padding: 3px 10px;
  border-radius: 20px;
  font-weight: 600;
}

/* Status / connecting */
.lk-status {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: #94a3b8;
  gap: 16px;
  padding: 40px;
}
.lk-error { color: #fca5a5; }

.lk-spinner {
  width: 40px;
  height: 40px;
  border: 3px solid #334155;
  border-top-color: #3b82f6;
  border-radius: 50%;
  animation: spin .8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

/* Video grid */
.lk-grid {
  flex: 1;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 8px;
  padding: 16px;
  overflow-y: auto;
  align-content: start;
  background: #0f172a;
}

.lk-tile {
  position: relative;
  background: #1e293b;
  border-radius: 10px;
  aspect-ratio: 16/9;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
}

.lk-video {
  width: 100%;
  height: 100%;
  object-fit: cover;
  transform: scaleX(-1); /* mirror local */
}

.lk-avatar {
  width: 64px;
  height: 64px;
  background: #1d4ed8;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 28px;
  font-weight: 700;
  color: #fff;
}

.lk-name-tag {
  position: absolute;
  bottom: 8px;
  left: 8px;
  background: rgba(0,0,0,.6);
  color: #e2e8f0;
  font-size: 12px;
  padding: 3px 8px;
  border-radius: 6px;
  display: flex;
  align-items: center;
  gap: 6px;
}

.lk-muted-icon { font-size: 11px; }

/* Controls */
.lk-controls {
  background: #1e293b;
  border-top: 1px solid #334155;
  padding: 12px 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  flex-shrink: 0;
}

.lk-ctrl-btn {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  padding: 10px 18px;
  background: #334155;
  color: #94a3b8;
  border-radius: 8px;
  font-size: 12px;
  transition: all .15s;
  min-width: 80px;
  cursor: pointer;
  border: none;
}
.lk-ctrl-btn span:first-child { font-size: 20px; }
.lk-ctrl-btn:hover { background: #475569; color: #e2e8f0; }
.lk-ctrl-btn.active { background: #1d4ed8; color: #fff; }
.lk-ctrl-btn.lk-leave { background: #dc2626; color: #fff; }
.lk-ctrl-btn.lk-leave:hover { background: #b91c1c; }
</style>
