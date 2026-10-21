<script setup>
import AgentStatus from './AgentStatus.vue'
import { computed, ref } from 'vue'
import BriefPlanConfirm from './BriefPlanConfirm.vue'
import CategoryConfirm from './CategoryConfirm.vue'
import QuestionForm from './QuestionForm.vue'

// message: { role: 'user' | 'assistant', text, imageUrl?, steps?, error?, candidates?, rejected?, perCategory?, categories?,
//            proposed?, sourceErrors?, questions?, selectable?, briefPlan?: { sections, autoSections }, output? }

const LICENSE_LABEL = { confirmed: '상업 이용 가능', unclear: '확인 필요', restricted: '제한됨' }
const props = defineProps({
  message: { type: Object, required: true },
  now: { type: Number, required: true },
  busy: { type: Boolean, default: false },
})
const emit = defineEmits(['answer', 'confirm', 'select', 'brief'])

// ── 레퍼런스 이미지 선택 (message.selectable 일 때) ─────────────────────────
const picked = ref([]) // 사용자가 클릭해서 고른 이미지 id
const saveUnverified = ref(false)
const selectionLocked = ref(false) // 선택을 보낸 뒤에는 바꿀 수 없다

const pickedCandidates = computed(() => (props.message.candidates ?? []).filter((c) => picked.value.includes(c.id)))
const unclearCount = computed(() => pickedCandidates.value.filter((c) => c.license === 'unclear').length)
const restrictedCount = computed(() => pickedCandidates.value.filter((c) => c.license === 'restricted').length)
const canSelect = computed(() => !selectionLocked.value && !props.busy)

function isPicked(id) {
  return picked.value.includes(id)
}

function toggle(id) {
  if (!canSelect.value) return
  picked.value = isPicked(id) ? picked.value.filter((x) => x !== id) : [...picked.value, id]
}

function submitSelection() {
  if (!canSelect.value || !picked.value.length) return
  selectionLocked.value = true
  emit('select', { message: props.message, selectedIds: picked.value, saveUnverified: saveUnverified.value })
}

// 확정된 카테고리별로 후보 이미지를 묶는다 (카테고리 순서 유지)
const groups = computed(() =>
  (props.message.categories ?? []).map((cat) => ({
    ...cat,
    items: (props.message.candidates ?? []).filter((c) => c.topic === cat.name),
    rejected: (props.message.rejected ?? []).filter((c) => c.topic === cat.name),
  })),
)
</script>

<template>
  <div class="message" :class="message.role">
    <div v-if="message.role === 'user'" class="bubble">
      <img v-if="message.imageUrl" :src="message.imageUrl" alt="첨부 이미지" class="attached" />
      <p class="text">{{ message.text }}</p>
    </div>

    <div v-else class="assistant">
      <AgentStatus v-if="message.steps?.length" :steps="message.steps" :now="now" />
      <p v-if="message.text" class="text" :class="{ error: message.error }">{{ message.text }}</p>

      <QuestionForm v-if="message.questions?.length" :questions="message.questions" :disabled="busy"
        @submit="emit('answer', { message, answers: $event })" />

      <CategoryConfirm v-if="message.proposed?.length" :categories="message.proposed" :disabled="busy"
        @submit="emit('confirm', { message, ...$event })" />

      <section v-if="groups.length" class="candidates">
        <p v-if="message.sourceErrors?.length" class="warn">
          일부 출처가 응답하지 않았어요: {{ message.sourceErrors.join(', ') }}
        </p>
        <div v-for="g in groups" :key="g.name" class="group">
          <h2>
            {{ g.name }}
            <span class="count">
              {{ g.items.length }}개<template v-if="message.perCategory && g.items.length < message.perCategory">
                (요청 {{ message.perCategory }}개 중 적합한 이미지만 남겼어요)</template>
            </span>
          </h2>
          <p v-if="g.reason" class="reason">{{ g.reason }}</p>
          <p v-for="rule in g.applied_rules" :key="rule" class="rule">세계관 반영 · {{ rule }}</p>
          <p class="queries">
            검색에 사용한 단어
            <span v-for="q in g.queries" :key="q" class="chip">{{ q }}</span>
          </p>
          <ul v-if="g.items.length" class="grid">
            <li v-for="c in g.items" :key="c.id" class="card" :class="{ picked: isPicked(c.id) }">
              <button v-if="message.selectable" type="button" class="thumb" :aria-pressed="isPicked(c.id)"
                :aria-label="`${c.title || '레퍼런스 이미지'} 선택`" :disabled="!canSelect" @click="toggle(c.id)">
                <img :src="c.thumbnail_url" :alt="c.title || '레퍼런스 이미지'" loading="lazy" />
                <span class="check" aria-hidden="true">{{ isPicked(c.id) ? '✓' : '' }}</span>
              </button>
              <a v-else :href="c.source_url" target="_blank" rel="noopener noreferrer">
                <img :src="c.thumbnail_url" :alt="c.title || '레퍼런스 이미지'" loading="lazy" />
              </a>
              <div class="meta">
                <span v-if="c.score != null" class="fit">적합도 {{ Math.round(c.score * 10) }}/10</span>
                <span class="badge" :class="c.license">{{ LICENSE_LABEL[c.license] }}</span>
                <span class="license">{{ c.license_detail }}</span>
                <span v-if="c.review" class="review">{{ c.review }}</span>
                <span class="found-by">{{ c.reason }}</span>
                <span class="source">{{ c.source_name }}<template v-if="c.creator"> · {{ c.creator }}</template></span>
                <a v-if="message.selectable" class="open" :href="c.source_url" target="_blank" rel="noopener noreferrer">원본 열기</a>
              </div>
            </li>
          </ul>
          <p v-else class="warn">조건에 맞는 이미지를 찾지 못했어요.</p>

          <details v-if="g.rejected.length" class="rejected">
            <summary>검토에서 제외된 이미지 {{ g.rejected.length }}개</summary>
            <ul>
              <li v-for="c in g.rejected" :key="c.id">
                <a :href="c.source_url" target="_blank" rel="noopener noreferrer">
                  <img :src="c.thumbnail_url" :alt="c.title || '제외된 이미지'" loading="lazy" />
                </a>
                <span>{{ c.review }}</span>
              </li>
            </ul>
          </details>
        </div>

        <div v-if="message.selectable" class="selection-bar">
          <strong>{{ picked.length }}장 선택</strong>
          <label v-if="unclearCount" class="unverified">
            <input v-model="saveUnverified" type="checkbox" :disabled="selectionLocked" />
            라이선스를 확인하지 못한 {{ unclearCount }}장도 파일로 저장
          </label>
          <span v-if="restrictedCount" class="hint">제한됨 {{ restrictedCount }}장은 파일로 저장하지 않고 링크만 기록해요</span>
          <span v-else-if="unclearCount && !saveUnverified" class="hint">확인 필요 이미지는 체크하지 않으면 링크만 기록해요</span>
          <button type="button" class="make" :disabled="!picked.length || !canSelect" @click="submitSelection">
            {{ selectionLocked ? '선택을 보냈어요' : '이 이미지로 지시서 만들기' }}
          </button>
        </div>
      </section>

      <BriefPlanConfirm v-if="message.briefPlan" :sections="message.briefPlan.sections"
        :auto-sections="message.briefPlan.autoSections" :disabled="busy"
        @submit="emit('brief', { message, ...$event })" />

      <section v-if="message.output" class="output">
        <h2>저장 위치</h2>
        <p class="folder">{{ message.output.folder }}/</p>
        <ul>
          <li>{{ message.output.brief_file }} 와 references.json 을 만들었어요</li>
          <li>이미지 {{ message.output.saved }}장을 카테고리 폴더에 저장했어요</li>
          <li v-if="message.output.link_only">
            {{ message.output.link_only }}장은 라이선스를 확인하지 못했거나 제한되어 링크만 기록했어요
          </li>
          <li v-if="message.output.failed" class="fail">{{ message.output.failed }}장은 내려받지 못해 링크만 기록했어요</li>
        </ul>
        <details class="preview">
          <summary>{{ message.output.brief_file }} 미리보기</summary>
          <pre>{{ message.output.brief_markdown }}</pre>
        </details>
      </section>
    </div>
  </div>
</template>

<style scoped>
.message {
  display: flex;
}

.message.user {
  justify-content: flex-end;
}

.bubble {
  max-width: 80%;
  background: var(--surface);
  border-radius: var(--radius);
  padding: 10px 14px;
}

.attached {
  display: block;
  max-width: 100%;
  max-height: 240px;
  border-radius: 10px;
  margin-bottom: 8px;
}

.text {
  margin: 0;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.assistant {
  display: grid;
  gap: 10px;
  max-width: 100%;
}

.error {
  color: #8a3b2e;
}

.candidates {
  display: grid;
  gap: 20px;
}

.group h2 {
  margin: 0;
  font-size: 15px;
}

.queries {
  margin: 0 0 10px;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--text-muted);
}

.rule {
  margin: 0 0 4px;
  font-size: 12px;
  color: var(--accent-strong);
}

.chip {
  padding: 1px 8px;
  border-radius: 999px;
  background: var(--surface);
  border: 1px solid var(--border);
  color: var(--text);
}

.fit {
  font-weight: 600;
  color: var(--text);
}

.review {
  color: var(--text);
  line-height: 1.4;
}

.rejected {
  margin-top: 10px;
  font-size: 13px;
  color: var(--text-muted);
}

.rejected summary {
  cursor: pointer;
}

.rejected ul {
  list-style: none;
  margin: 8px 0 0;
  padding: 0;
  display: grid;
  gap: 8px;
}

.rejected li {
  display: flex;
  align-items: center;
  gap: 10px;
}

.rejected img {
  width: 56px;
  height: 56px;
  object-fit: cover;
  border-radius: 8px;
  display: block;
  opacity: 0.8;
}

.found-by {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.count {
  font-weight: 400;
  font-size: 13px;
  color: var(--text-muted);
}

.reason {
  margin: 2px 0 8px;
  font-size: 13px;
  color: var(--text-muted);
}

.warn {
  margin: 0 0 8px;
  font-size: 13px;
  color: var(--text-muted);
}

.grid {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: 12px;
}

.card {
  background: var(--surface);
  border-radius: 12px;
  overflow: hidden;
  display: grid;
  align-content: start;
}

.card img {
  display: block;
  width: 100%;
  aspect-ratio: 4 / 3;
  object-fit: cover;
  background: var(--border);
}

.meta {
  padding: 8px 10px 10px;
  display: grid;
  gap: 2px;
  font-size: 12px;
  color: var(--text-muted);
}

.badge {
  justify-self: start;
  padding: 1px 8px;
  border-radius: 999px;
  font-weight: 600;
  color: var(--bg);
  background: var(--accent-strong);
}

.badge.unclear,
.badge.restricted {
  background: var(--text-muted);
}

.source {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.thumb {
  position: relative;
  display: block;
  width: 100%;
  padding: 0;
  border: 0;
  background: none;
  cursor: pointer;
}

.thumb:disabled {
  cursor: default;
}

.check {
  position: absolute;
  top: 8px;
  right: 8px;
  width: 24px;
  height: 24px;
  display: grid;
  place-items: center;
  border: 2px solid var(--bg);
  border-radius: 50%;
  background: color-mix(in srgb, var(--text) 35%, transparent);
  color: var(--bg);
  font-size: 14px;
  font-weight: 700;
}

.card.picked {
  outline: 3px solid var(--accent-strong);
  outline-offset: -3px;
}

.card.picked .check {
  background: var(--accent-strong);
}

.open {
  color: var(--accent-strong);
  font-size: 12px;
}

.selection-bar {
  position: sticky;
  bottom: 12px;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 14px;
  padding: 12px 14px;
  background: var(--bg);
  border: 1px solid var(--accent);
  border-radius: var(--radius);
  box-shadow: 0 4px 16px color-mix(in srgb, var(--text) 12%, transparent);
}

.unverified {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
}

.unverified input {
  accent-color: var(--accent-strong);
}

.hint {
  font-size: 12px;
  color: var(--text-muted);
}

.make {
  margin-left: auto;
  padding: 8px 18px;
  border: 0;
  border-radius: 999px;
  background: var(--accent-strong);
  color: var(--bg);
  font-weight: 600;
}

.make:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.output {
  padding: 14px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
}

.output h2 {
  margin: 0 0 4px;
  font-size: 15px;
}

.output .folder {
  margin: 0 0 8px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 14px;
  color: var(--accent-strong);
  overflow-wrap: anywhere;
}

.output ul {
  margin: 0 0 10px;
  padding-left: 18px;
}

.output .fail {
  color: #8a3b2e;
}

.preview summary {
  cursor: pointer;
}

.preview pre {
  margin: 8px 0 0;
  padding: 12px;
  max-height: 420px;
  overflow: auto;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 10px;
  font-size: 13px;
  line-height: 1.5;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
</style>
