<script setup>
import AgentStatus from './AgentStatus.vue'
import { computed } from 'vue'
import CategoryConfirm from './CategoryConfirm.vue'
import QuestionForm from './QuestionForm.vue'

// message: { role: 'user' | 'assistant', text, imageUrl?, steps?, error?, candidates?, rejected?, perCategory?, categories?, proposed?, sourceErrors?, questions? }

const LICENSE_LABEL = { confirmed: '상업 이용 가능', unclear: '확인 필요', restricted: '제한됨' }
const props = defineProps({
  message: { type: Object, required: true },
  now: { type: Number, required: true },
  busy: { type: Boolean, default: false },
})
const emit = defineEmits(['answer', 'confirm'])

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
            <li v-for="c in g.items" :key="c.id" class="card">
              <a :href="c.source_url" target="_blank" rel="noopener noreferrer">
                <img :src="c.thumbnail_url" :alt="c.title || '레퍼런스 이미지'" loading="lazy" />
              </a>
              <div class="meta">
                <span v-if="c.score != null" class="fit">적합도 {{ Math.round(c.score * 10) }}/10</span>
                <span class="badge" :class="c.license">{{ LICENSE_LABEL[c.license] }}</span>
                <span class="license">{{ c.license_detail }}</span>
                <span v-if="c.review" class="review">{{ c.review }}</span>
                <span class="found-by">{{ c.reason }}</span>
                <span class="source">{{ c.source_name }}<template v-if="c.creator"> · {{ c.creator }}</template></span>
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
</style>
