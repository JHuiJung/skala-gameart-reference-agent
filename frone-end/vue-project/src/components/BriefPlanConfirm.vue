<script setup>
import { computed, reactive, ref } from 'vue'

// 지시서에 무엇을 쓸지에 대한 계획을 사용자가 확인·수정하는 폼.
// 섹션 제목과 내용(outline)을 고치고, 순서를 바꾸고, 지우거나 새로 추가할 수 있다.
// sections: [{ heading, outline }], autoSections: 시스템이 자동으로 쓰는 섹션 이름들 (수정 불가)
const props = defineProps({
  sections: { type: Array, required: true },
  autoSections: { type: Array, default: () => [] },
  disabled: { type: Boolean, default: false },
})
const emit = defineEmits(['submit'])

const MAX_SECTIONS = 15
let nextKey = 0
const rows = reactive(props.sections.map((s) => ({ key: nextKey++, heading: s.heading, outline: s.outline })))
const notes = ref('')
const submitted = ref(false)

const locked = computed(() => submitted.value || props.disabled)

// 제출 전에 막아야 하는 문제 (서버도 같은 규칙으로 검사한다)
const problem = computed(() => {
  const headings = rows.map((r) => r.heading.trim())
  if (!rows.length) return '섹션이 하나는 있어야 해요.'
  if (headings.some((h) => !h)) return '제목이 비어 있는 섹션이 있어요.'
  if (new Set(headings).size !== headings.length) return '제목이 같은 섹션이 있어요.'
  if (headings.some((h) => props.autoSections.includes(h))) return '자동으로 작성되는 섹션과 제목이 같아요.'
  return ''
})
const canSubmit = computed(() => !locked.value && !problem.value)

function move(index, step) {
  const target = index + step
  if (target < 0 || target >= rows.length) return
  rows.splice(target, 0, rows.splice(index, 1)[0])
}

function addSection() {
  if (rows.length < MAX_SECTIONS) rows.push({ key: nextKey++, heading: '', outline: '' })
}

function submit() {
  if (!canSubmit.value) return
  submitted.value = true
  emit('submit', {
    sections: rows.map((r) => ({ heading: r.heading.trim(), outline: r.outline.trim() })),
    notes: notes.value.trim(),
  })
}
</script>

<template>
  <form class="plan" @submit.prevent="submit">
    <ol class="sections">
      <li v-for="(row, i) in rows" :key="row.key">
        <div class="head">
          <span class="no">{{ i + 1 }}</span>
          <input v-model="row.heading" type="text" maxlength="60" placeholder="섹션 제목" :disabled="locked"
            :aria-label="`${i + 1}번 섹션 제목`" />
          <button type="button" class="icon" :disabled="locked || i === 0" aria-label="위로" @click="move(i, -1)">↑</button>
          <button type="button" class="icon" :disabled="locked || i === rows.length - 1" aria-label="아래로"
            @click="move(i, 1)">↓</button>
          <button type="button" class="icon" :disabled="locked || rows.length === 1" aria-label="섹션 삭제"
            @click="rows.splice(i, 1)">✕</button>
        </div>
        <textarea v-model="row.outline" rows="3" maxlength="1500" placeholder="이 섹션에 쓸 내용"
          :disabled="locked" :aria-label="`${i + 1}번 섹션 내용`"></textarea>
      </li>
    </ol>

    <button type="button" class="add" :disabled="locked || rows.length >= MAX_SECTIONS" @click="addSection">
      + 섹션 추가
    </button>

    <p v-if="autoSections.length" class="auto">
      자동으로 작성돼요 (수정 불가):
      <span v-for="name in autoSections" :key="name" class="chip">{{ name }}</span>
    </p>

    <div class="notes">
      <label for="brief-notes">AI에게 추가로 요청할 내용 (선택)</label>
      <textarea id="brief-notes" v-model="notes" rows="2" maxlength="1500" :disabled="locked"
        placeholder="예: 아트팀 신입도 이해할 수 있게 쉬운 말로 써주세요"></textarea>
    </div>

    <div class="footer">
      <span class="note" :class="{ warn: problem }">
        {{ submitted ? '지시서 작성을 시작했어요' : problem || '내용을 고치거나 순서를 바꿔도 돼요' }}
      </span>
      <button type="submit" class="submit" :disabled="!canSubmit">이대로 작성 시작</button>
    </div>
  </form>
</template>

<style scoped>
.plan {
  display: grid;
  gap: 12px;
  padding: 14px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
}

.sections {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 12px;
}

.sections li {
  display: grid;
  gap: 6px;
}

.head {
  display: flex;
  align-items: center;
  gap: 6px;
}

.no {
  width: 22px;
  height: 22px;
  flex: none;
  display: grid;
  place-items: center;
  border-radius: 50%;
  background: var(--accent-strong);
  color: var(--bg);
  font-size: 12px;
  font-weight: 600;
}

input[type='text'],
textarea {
  width: 100%;
  padding: 8px 10px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--bg);
  outline: none;
}

input[type='text'] {
  font-weight: 600;
}

textarea {
  resize: vertical;
}

input:focus,
textarea:focus {
  border-color: var(--accent);
}

.icon {
  flex: none;
  width: 30px;
  height: 30px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg);
  color: var(--text-muted);
}

.icon:hover:not(:disabled) {
  color: var(--text);
  border-color: var(--accent);
}

.add {
  justify-self: start;
  padding: 6px 14px;
  border: 1px dashed var(--accent);
  border-radius: 999px;
  background: transparent;
  color: var(--accent-strong);
}

.auto {
  margin: 0;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: var(--text-muted);
}

.chip {
  padding: 1px 8px;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: var(--bg);
  color: var(--text);
}

.notes {
  display: grid;
  gap: 6px;
}

.notes label {
  font-weight: 600;
}

button:disabled,
input:disabled,
textarea:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.note {
  font-size: 13px;
  color: var(--text-muted);
}

.note.warn {
  color: #8a3b2e;
}

.submit {
  padding: 8px 18px;
  border: 0;
  border-radius: 999px;
  background: var(--accent-strong);
  color: var(--bg);
  font-weight: 600;
}
</style>
