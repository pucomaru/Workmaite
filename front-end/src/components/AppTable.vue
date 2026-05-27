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
            :class="[col.class, col.sortKey ? 'sortable-th' : '']"
            @click="col.sortKey ? handleSort(col.sortKey) : undefined"
          >
            <span class="th-content">
              {{ col.label ?? '' }}
              <span v-if="col.sortKey" class="sort-icons">
                <svg class="sort-icon" :class="{ active: sortKey === col.sortKey && sortDir === 'asc' }"
                  width="8" height="8" viewBox="0 0 8 8" fill="currentColor">
                  <path d="M4 1 L7 6 L1 6 Z"/>
                </svg>
                <svg class="sort-icon" :class="{ active: sortKey === col.sortKey && sortDir === 'desc' }"
                  width="8" height="8" viewBox="0 0 8 8" fill="currentColor">
                  <path d="M4 7 L1 2 L7 2 Z"/>
                </svg>
              </span>
            </span>
            <div
              v-if="i < columns.length - 1 && !col.noResize && !columns[i + 1]?.noResize"
              class="col-resize-handle"
              @mousedown.prevent.stop="startResize($event, i)"
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

const props = defineProps({
  columns: { type: Array, default: () => [] },
  dark: { type: Boolean, default: false },
  sortKey: { type: String, default: null },
  sortDir: { type: String, default: null },  // 'asc' | 'desc' | null
})

const emit = defineEmits(['sort'])

function handleSort(key) {
  if (props.sortKey === key) {
    if (props.sortDir === 'asc') emit('sort', { key, dir: 'desc' })
    else if (props.sortDir === 'desc') emit('sort', { key: null, dir: null })
    else emit('sort', { key, dir: 'asc' })
  } else {
    emit('sort', { key, dir: 'asc' })
  }
}

const colWidths = ref([])
let resizing = null

const MIN_COL_WIDTH = 40

function startResize(e, colIndex) {
  const th = e.target.closest('th')
  const startX = e.clientX

  if (!colWidths.value.length) {
    const allThs = th.closest('tr').querySelectorAll('th')
    colWidths.value = Array.from(allThs).map(h => h.offsetWidth)
  }

  resizing = {
    colIndex,
    startX,
    startWidth: colWidths.value[colIndex],
    nextStartWidth: colWidths.value[colIndex + 1],
  }

  const onMouseMove = (ev) => {
    if (!resizing) return
    const dx = ev.clientX - resizing.startX

    // 양쪽 모두 최솟값 보장
    const maxDx = resizing.nextStartWidth - MIN_COL_WIDTH
    const minDx = -(resizing.startWidth - MIN_COL_WIDTH)
    const clampedDx = Math.max(minDx, Math.min(maxDx, dx))

    const newCols = [...colWidths.value]
    newCols[resizing.colIndex] = resizing.startWidth + clampedDx
    newCols[resizing.colIndex + 1] = resizing.nextStartWidth - clampedDx
    colWidths.value = newCols
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
.th-content {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}
.sortable-th {
  cursor: pointer;
}
.sortable-th:hover {
  color: #334155;
  background: #f1f5f9;
}
.sort-icons {
  display: inline-flex;
  flex-direction: column;
  gap: 1px;
  opacity: 0.3;
  transition: opacity 0.15s;
}
.sortable-th:hover .sort-icons {
  opacity: 0.6;
}
.sort-icon {
  display: block;
  color: #94a3b8;
  transition: color 0.15s;
}
.sort-icon.active {
  color: #3b82f6;
  opacity: 1 !important;
}
.sortable-th:hover .sort-icons,
.sort-icon.active {
  opacity: 1;
}
.app-table th:last-child {
  position: sticky;
  right: 0;
  z-index: 2;
}
.app-table td {
  padding: 11px 16px;
  vertical-align: middle;
  color: #1e293b;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 0;
}
.app-table td:last-child {
  position: sticky;
  right: 0;
  background: #fff;
  z-index: 1;
  max-width: none;
  overflow: visible;
  white-space: nowrap;
}
/* Column resize handle – doubles as visible divider */
.col-resize-handle {
  position: absolute;
  right: 0;
  top: 0;
  height: 100%;
  width: 2px;
  background: #e2e8f0;
  cursor: col-resize;
  z-index: 1;
  transition: background 0.15s;
}
.col-resize-handle:hover,
.col-resize-handle:active {
  background: #94a3b8;
  width: 3px;
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
.app-table-dark .sortable-th:hover {
  color: #94a3b8;
  background: rgba(255,255,255,.05);
}
.app-table-dark .sort-icon {
  color: #475569;
}
.app-table-dark .app-table th:last-child {
  background: #1e2d3e;
}
.app-table-dark .app-table td {
  color: #e2e8f0;
  border-right-color: rgba(255,255,255,.05);
}
.app-table-dark .app-table td:last-child {
  background: #1e293b;
}
.app-table-dark .col-resize-handle {
  background: rgba(255,255,255,.12);
}
.app-table-dark .col-resize-handle:hover,
.app-table-dark .col-resize-handle:active {
  background: rgba(255,255,255,.35);
}
</style>
