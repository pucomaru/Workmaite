<template>
  <div class="app-table-wrap" :class="{ 'app-table-dark': dark }">
    <table class="app-table">
      <thead>
        <tr>
          <th
            v-for="(col, i) in columns"
            :key="col.key ?? col.label ?? i"
            :style="col.width ? { width: col.width } : (col.style || {})"
            :class="col.class"
          >{{ col.label ?? '' }}</th>
        </tr>
      </thead>
      <tbody>
        <slot />
      </tbody>
    </table>
  </div>
</template>

<script setup>
defineProps({
  columns: { type: Array, default: () => [] },
  dark: { type: Boolean, default: false }
})
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
  padding: 11px 16px;
  font-size: 11px;
  font-weight: 700;
  color: #64748b;
  text-transform: uppercase;
  letter-spacing: .04em;
  text-align: left;
  white-space: nowrap;
  background: #f8fafc;
}
.app-table td {
  padding: 11px 16px;
  vertical-align: middle;
  color: #1e293b;
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
}
</style>
