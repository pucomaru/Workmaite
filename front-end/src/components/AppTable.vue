<template>
  <div class="app-table-wrap" :class="{ 'app-table-dark': dark }">
    <table class="app-table" :style="colWidths.length ? { tableLayout: 'fixed' } : {}">
      <colgroup>
        <col
          v-for="(col, i) in columns"
          :key="i"
          :style="colWidths[i] ? { width: colWidths[i] + 'px' } : (col.width ? { width: col.width } : {})"
        />
      </colgroup>
      <thead>
        <tr>
          <th
            v-for="(col, i) in columns"
            :key="col.key ?? col.label ?? i"
            :class="col.class"
          >
            {{ col.label ?? '' }}
            <div
              v-if="i < columns.length - 1"
              class="col-resize-handle"
              @mousedown.prevent="startResize($event, i)"
            ></div>
          </th>
        </tr>
      </thead>
      <tbody>
        <slot />
      </tbody>
    </table>
  </div>
</template>

<script setup>
import { ref } from 'vue'

defineProps({
  columns: { type: Array, default: () => [] },
  dark: { type: Boolean, default: false }
})

const colWidths = ref([])
let resizing = null

function startResize(e, colIndex) {
  const th = e.target.closest('th')
  const startX = e.clientX
  const startWidth = th.offsetWidth

  if (!colWidths.value.length) {
    const allThs = th.closest('tr').querySelectorAll('th')
    colWidths.value = Array.from(allThs).map(h => h.offsetWidth)
  }

  resizing = { colIndex, startX, startWidth }

  const onMouseMove = (ev) => {
    if (!resizing) return
    const dx = ev.clientX - resizing.startX
    const newWidth = Math.max(40, resizing.startWidth + dx)
    colWidths.value = colWidths.value.map((w, i) => i === resizing.colIndex ? newWidth : w)
  }

  const onMouseUp = () => {
    resizing = null
    window.removeEventListener('mousemove', onMouseMove)
    window.removeEventListener('mouseup', onMouseUp)
  }

  window.addEventListener('mousemove', onMouseMove)
  window.addEventListener('mouseup', onMouseUp)
}
</script>

<style>
/* ── Light (default) ── */
.app-table-wrap {
  overflow-x: auto;
  border-radius: 10px;
  border: 1px solid #e2e8f0;
  background: #fff;
}
.app-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.app-table thead tr {
  border-bottom: 1px solid #e2e8f0;
  background: #f8fafc;
}
.app-table th {
  position: relative;
  padding: 11px 16px;
  font-size: 11px;
  font-weight: 700;
  color: #64748b;
  text-transform: uppercase;
  letter-spacing: .04em;
  text-align: left;
  white-space: nowrap;
  background: #f8fafc;
  user-select: none;
}
.app-table td {
  padding: 11px 16px;
  vertical-align: middle;
  color: #1e293b;
  border-right: 1px solid #f1f5f9;
}
.app-table td:last-child {
  border-right: none;
}
/* Column resize handle – doubles as visible divider */
.col-resize-handle {
  position: absolute;
  right: 0;
  top: 0;
  height: 100%;
  width: 3px;
  background: #e2e8f0;
  cursor: col-resize;
  z-index: 1;
  transition: background 0.15s;
}
.col-resize-handle:hover,
.col-resize-handle:active {
  background: #94a3b8;
  width: 4px;
}
/* ── Dark variant ── */
.app-table-dark {
  border-color: rgba(255,255,255,.09);
  background: #1e293b;
}
.app-table-dark .app-table thead tr {
  border-bottom-color: rgba(255,255,255,.09);
  background: rgba(255,255,255,.03);
}
.app-table-dark .app-table th {
  background: transparent;
  color: #64748b;
}
.app-table-dark .app-table td {
  color: #e2e8f0;
  border-right-color: rgba(255,255,255,.05);
}
.app-table-dark .col-resize-handle {
  background: rgba(255,255,255,.12);
}
.app-table-dark .col-resize-handle:hover,
.app-table-dark .col-resize-handle:active {
  background: rgba(255,255,255,.35);
}
</style>
