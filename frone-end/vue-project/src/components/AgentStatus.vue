<script setup>
// 에이전트가 거친 단계 목록. 진행 중인 단계는 실시간 경과 시간, 끝난 단계는 걸린 시간을 보여준다.
// steps: [{ label, detail?, startedAt, endedAt }]  (시간은 ms). detail 은 진행 중인 단계에서만 보여준다
defineProps({
  steps: { type: Array, required: true },
  now: { type: Number, required: true },
})

function seconds(step, now) {
  return (((step.endedAt ?? now) - step.startedAt) / 1000).toFixed(1)
}
</script>

<template>
  <ul class="steps">
    <li v-for="(step, i) in steps" :key="i" :class="{ active: !step.endedAt }">
      <span class="dot" aria-hidden="true"></span>
      <span class="label">
        {{ step.label }}{{ step.endedAt ? ' 완료' : '…' }}
        <span v-if="!step.endedAt && step.detail" class="detail">{{ step.detail }}</span>
      </span>
      <span class="time">{{ seconds(step, now) }}초</span>
    </li>
  </ul>
</template>

<style scoped>
.steps {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 6px;
  font-size: 14px;
  color: var(--text-muted);
}

li {
  display: flex;
  align-items: baseline;
  gap: 10px;
}

.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--accent);
  flex: none;
}

li.active {
  color: var(--text);
}

li.active .dot {
  animation: pulse 1.2s ease-in-out infinite;
}

.detail {
  margin-left: 8px;
  color: var(--text-muted);
  font-size: 13px;
}

.time {
  font-variant-numeric: tabular-nums;
}

@keyframes pulse {
  50% {
    opacity: 0.25;
    transform: scale(0.7);
  }
}

@media (prefers-reduced-motion: reduce) {
  li.active .dot {
    animation: none;
  }
}
</style>
