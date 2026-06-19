<script setup>
import { inject } from 'vue'
import MeetingSettingsModal from './MeetingSettingsModal.vue'

const { settingsModal, nightMode, closeSettings, savingSettings, saveSettings, deleteSettings } =
  inject('archiveModals')
</script>

<template>
  <MeetingSettingsModal
    :settings="settingsModal"
    :night-mode="nightMode"
    :saving="savingSettings"
    @close="closeSettings"
    @save="saveSettings"
    @delete="deleteSettings"
  />
</template>
