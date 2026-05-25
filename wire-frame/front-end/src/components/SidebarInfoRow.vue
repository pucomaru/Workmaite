<template>
  <div class="sb-info-row">
    <span class="sb-info-key">{{ label }}</span>
    <span class="sb-info-val"><slot>{{ value }}</slot></span>
  </div>
</template>

<script setup>
defineProps({ label: String, value: { type: [String, Number], default: '' } })
</script>

<style>
.sb-info-row { display:flex;align-items:baseline;gap:10px; }
.sb-info-key { flex-shrink:0;width:58px;font-size:11px;font-weight:600;color:#777;line-height:1.5; }
.sb-info-val { flex:1;font-size:11px;color:#aaa;line-height:1.5; }
.day-mode .sb-info-key { color:#64748b; }
.day-mode .sb-info-val { color:#1e293b; }
</style>
