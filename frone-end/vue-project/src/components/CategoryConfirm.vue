<script setup>
import { computed, reactive, ref } from 'vue'

// AI 가 제안한 레퍼런스 카테고리를 사용자가 첨삭하는 폼.
// 제안된 카테고리는 체크를 해제해서 빼고, 새 카테고리는 직접 입력해서 추가한다.
// categories: [{ name, reason, applied_rules }]  (applied_rules: 검색어에 반영한 세계관·기획 가이드 규칙)
const props = defineProps({
  categories: { type: Array, required: true },
  disabled: { type: Boolean, default: false },
})
const emit = defineEmits(['submit'])

const MAX = 8
const MIN_IMAGES = 1
const MAX_IMAGES = 10

const checked = reactive(Object.fromEntries(props.categories.map((c) => [c.name, true])))
const added = ref([]) // 사용자가 추가한 카테고리 이름
const draft = ref('')
const perCategory = ref(5) // 카테고리당 보여줄 이미지 수
const submitted = ref(false)

const selected = computed(() => [
  ...props.categories.filter((c) => checked[c.name]).map((c) => c.name),
  ...added.value,
])
const locked = computed(() => submitted.value || props.disabled)
const canSubmit = computed(() => !locked.value && selected.value.length >= 1 && selected.value.length <= MAX)

function addCategory() {
  const name = draft.value.trim().slice(0, 40)
  const exists = props.categories.some((c) => c.name === name) || added.value.includes(name)
  if (name && !exists && selected.value.length < MAX) added.value.push(name)
  draft.value = ''
}

function onDraftKeydown(e) {
  // 한글 조합 중 Enter 는 추가하지 않는다
  if (e.key === 'Enter' && !e.isComposing) {
    e.preventDefault()
    addCategory()
  }
}

function submit() {
  if (!canSubmit.value) return
  submitted.value = true
  emit('submit', { categories: selected.value, perCategory: perCategory.value })
}
</script>

<template>
  <form class="confirm" @submit.prevent="submit">
    <p class="summary">
      <strong>{{ selected.length }}개</strong> 카테고리 [{{ selected.join(', ') }}]로 이미지 검색할까요?
    </p>

    <ul class="list">
      <li v-for="c in categories" :key="c.name">
        <label>
          <input v-model="checked[c.name]" type="checkbox" :disabled="locked" />
          <span class="name">{{ c.name }}</span>
        </label>
        <span class="reason">{{ c.reason }}</span>
        <span v-for="rule in c.applied_rules" :key="rule" class="rule">세계관 반영 · {{ rule }}</span>
      </li>
      <li v-for="name in added" :key="name" class="added">
        <label>
          <input type="checkbox" checked disabled />
          <span class="name">{{ name }}</span>
        </label>
        <button type="button" class="remove" :disabled="locked" @click="added = added.filter((n) => n !== name)">
          삭제
        </button>
      </li>
    </ul>

    <div class="add">
      <input v-model="draft" type="text" placeholder="카테고리 추가 (예: 눈 덮인 마을 가로등)" maxlength="40"
        :disabled="locked || selected.length >= MAX" @keydown="onDraftKeydown" />
      <button type="button" :disabled="locked || !draft.trim()" @click="addCategory">추가</button>
    </div>

    <div class="count">
      <label for="per-category">카테고리당 이미지 수</label>
      <input id="per-category" v-model.number="perCategory" type="range" :min="MIN_IMAGES" :max="MAX_IMAGES"
        step="1" :disabled="locked" />
      <output for="per-category">{{ perCategory }}개</output>
    </div>

    <div class="footer">
      <span class="note">
        {{ submitted ? '검색을 시작했어요' : selected.length >= MAX ? `최대 ${MAX}개까지 선택할 수 있어요` : '체크를 해제해서 빼거나 직접 추가할 수 있어요' }}
      </span>
      <button type="submit" class="submit" :disabled="!canSubmit">이대로 검색</button>
    </div>
  </form>
</template>

<style scoped>
.confirm {
  display: grid;
  gap: 12px;
  padding: 14px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
}

.summary {
  margin: 0;
}

.list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 8px;
}

.list li {
  display: grid;
  gap: 2px;
}

label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
  cursor: pointer;
}

input[type='checkbox'] {
  accent-color: var(--accent-strong);
  width: 16px;
  height: 16px;
}

.reason {
  margin-left: 24px;
  font-size: 13px;
  color: var(--text-muted);
}

.rule {
  margin-left: 24px;
  font-size: 12px;
  color: var(--accent-strong);
}

.added {
  display: flex !important;
  justify-content: space-between;
  align-items: center;
}

.remove {
  border: 0;
  background: transparent;
  color: var(--text-muted);
  font-size: 13px;
  text-decoration: underline;
}

.add {
  display: flex;
  gap: 8px;
}

.add input {
  flex: 1;
  padding: 8px 10px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--bg);
  outline: none;
}

.add input:focus {
  border-color: var(--accent);
}

.add button {
  padding: 8px 14px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--bg);
}

button:disabled,
input:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.count {
  display: flex;
  align-items: center;
  gap: 12px;
}

.count label {
  cursor: default;
  font-weight: 600;
}

.count input[type='range'] {
  flex: 1;
  accent-color: var(--accent-strong);
}

.count output {
  min-width: 3ch;
  font-variant-numeric: tabular-nums;
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

.submit {
  padding: 8px 18px;
  border: 0;
  border-radius: 999px;
  background: var(--accent-strong);
  color: var(--bg);
  font-weight: 600;
}
</style>
