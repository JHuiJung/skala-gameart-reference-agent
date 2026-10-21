<script setup>
import { computed, nextTick, onBeforeUnmount, ref } from 'vue'
import AppHeader from '@/components/AppHeader.vue'
import ChatInput from '@/components/ChatInput.vue'
import ChatMessage from '@/components/ChatMessage.vue'
import { sendMessage } from '@/api/chat'

const messages = ref([])
const busy = ref(false)
const scroller = ref(null)

// 진행 중 단계의 경과 시간을 실시간으로 갱신하기 위한 현재 시각
const now = ref(Date.now())
const timer = setInterval(() => (now.value = Date.now()), 100)
onBeforeUnmount(() => clearInterval(timer))

const isEmpty = computed(() => messages.value.length === 0)

function scrollToBottom() {
  nextTick(() => {
    const el = scroller.value
    if (el) el.scrollTop = el.scrollHeight
  })
}

// 에이전트가 "지금 하는 일"을 바꿀 때마다 이전 단계를 닫고 새 단계를 시작한다
function setStatus(reply, label) {
  const t = Date.now()
  const last = reply.steps[reply.steps.length - 1]
  if (last && !last.endedAt) last.endedAt = t
  reply.steps.push({ label, startedAt: t, endedAt: null })
  scrollToBottom()
}

function finishSteps(reply) {
  const last = reply.steps[reply.steps.length - 1]
  if (last && !last.endedAt) last.endedAt = Date.now()
}

// 분석 결과, 관련 가이드, 검색 계획을 사람이 읽기 좋은 텍스트로 만든다
function formatResult({ analysis, guidelines, search_plan: plan }) {
  const guideLines = guidelines.map((g) => `· ${g.file} > ${g.section}`)
  const guideText = guideLines.length ? `\n\n참고한 내부 가이드\n${guideLines.join('\n')}` : ''
  const planText = `\n\n검색 계획\n키워드: ${plan.queries.join(', ')}\n제외어: ${plan.exclude_terms.join(', ')}\n분류 폴더: ${plan.topics.join(', ')}`
  return formatAnalysis(analysis) + guideText + planText
}

function formatAnalysis(a) {
  const rows = [
    ['대상', a.subject],
    ['분위기', a.mood.join(', ')],
    ['재질', a.materials.join(', ')],
    ['색상', a.colors.join(', ')],
    ['구도', a.composition],
    ['제외', a.exclude.join(', ')],
    ['이미지 요약', a.summary],
  ]
  return rows.filter(([, v]) => v).map(([k, v]) => `${k}: ${v}`).join('\n')
}

async function onSend({ text, image, imageUrl }) {
  messages.value.push({ role: 'user', text, imageUrl })
  messages.value.push({ role: 'assistant', text: '', steps: [] })
  const reply = messages.value[messages.value.length - 1]
  busy.value = true
  scrollToBottom()

  try {
    const result = await sendMessage({ text, image, onStatus: (label) => setStatus(reply, label) })
    finishSteps(reply)
    reply.text = formatResult(result)
  } catch (err) {
    finishSteps(reply)
    reply.error = true
    reply.text = `오류가 발생했어요. ${err.message}`
  } finally {
    busy.value = false
    scrollToBottom()
  }
}
</script>

<template>
  <div class="chat" :class="{ empty: isEmpty }">
    <AppHeader />

    <div v-if="!isEmpty" ref="scroller" class="scroller">
      <div class="messages">
        <ChatMessage v-for="(m, i) in messages" :key="i" :message="m" :now="now" />
      </div>
    </div>

    <main class="composer-area">
      <h1 v-if="isEmpty" class="greeting">어떤 레퍼런스를 찾아볼까요?</h1>
      <ChatInput :disabled="busy" @send="onSend" />
    </main>
  </div>
</template>

<style scoped>
.chat {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.scroller {
  flex: 1;
  overflow-y: auto;
}

.messages {
  max-width: var(--content-width);
  margin: 0 auto;
  padding: 8px 24px 24px;
  display: grid;
  gap: 24px;
}

.composer-area {
  width: 100%;
  max-width: var(--content-width);
  margin: 0 auto;
  padding: 0 24px 24px;
}

/* 첫 화면: 입력창을 화면 가운데에 둔다 */
.chat.empty .composer-area {
  margin-block: auto;
  padding-bottom: 12vh;
}

.greeting {
  margin: 0 0 24px;
  text-align: center;
  font-size: 28px;
  font-weight: 600;
  letter-spacing: -0.02em;
}

@media (max-width: 600px) {
  .messages,
  .composer-area {
    padding-inline: 16px;
  }

  .greeting {
    font-size: 22px;
  }
}
</style>
