<script setup>
import { computed, nextTick, onBeforeUnmount, ref } from 'vue'
import AppHeader from '@/components/AppHeader.vue'
import ChatInput from '@/components/ChatInput.vue'
import ChatMessage from '@/components/ChatMessage.vue'
import { sendAnswers, sendBrief, sendCategories, sendMessage, sendSelection } from '@/api/chat'

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

// 현재 진행 중인 단계 안의 세부 진행(예: "'겨울 외피' 검색 완료 (3/5)")을 갱신한다
function setDetail(reply, detail) {
  const last = reply.steps[reply.steps.length - 1]
  if (last && !last.endedAt) last.detail = detail
}

function finishSteps(reply) {
  const last = reply.steps[reply.steps.length - 1]
  if (last && !last.endedAt) last.endedAt = Date.now()
}

const TYPE_LABEL = { character: '캐릭터', background: '배경', prop: '소품', ui: 'UI' }

// 지금까지 확인된 필수 항목을 "항목: 값" 목록으로 만든다 (비어 있거나 '미정'인 것은 제외)
function formatDetails(details, labels) {
  return Object.entries(details)
    .filter(([, v]) => v && v !== '미정')
    .map(([k, v]) => `· ${labels[k]}: ${v}`)
    .join('\n')
}

// 에이전트가 되묻는 상황의 안내 문구
function formatQuestionIntro({ asset_type: type, questions, details, detail_labels: labels }) {
  if (type === 'unknown') return '입력만으로는 어떤 종류인지 알 수 없었어요. 종류를 골라주세요.'
  const known = formatDetails(details, labels)
  const knownText = known ? `\n\n확인된 내용\n${known}` : ''
  return `${TYPE_LABEL[type]} 제작에 필요한 정보 중 ${questions.length}가지가 빠져 있어요.${knownText}`
}

// 분석 결과와 관련 가이드를 사람이 읽기 좋은 텍스트로 만든다
function formatResult({ asset_type: type, analysis, guidelines, exclude_terms: excluded }) {
  const guideLines = guidelines.map((g) => `· ${g.file} > ${g.section}`)
  const guideText = guideLines.length ? `\n\n참고한 내부 가이드\n${guideLines.join('\n')}` : ''
  const excludeText = excluded.length ? `\n\n검색에서 제외한 단어: ${excluded.join(', ')}` : ''
  return `종류: ${TYPE_LABEL[type]}\n` + formatAnalysis(analysis) + guideText + excludeText
}

function formatAnalysis(a) {
  const rows = [
    ['요청 이해', a.goal],
    ['대상', a.subject],
    ['분위기', a.mood.join(', ')],
    ['재질', a.materials.join(', ')],
    ['색상', a.colors.join(', ')],
    ['구도', a.composition],
    ['제외', a.exclude.join(', ')],
    ['이미지 현재 모습', a.summary],
  ]
  return rows.filter(([, v]) => v).map(([k, v]) => `${k}: ${v}`).join('\n')
}

// 에이전트 요청 하나를 실행하고 진행 단계, 결과(또는 질문), 오류를 응답 메시지에 반영한다
async function runAgent(call, extra = {}) {
  messages.value.push({ role: 'assistant', text: '', steps: [], ...extra })
  const reply = messages.value[messages.value.length - 1]
  busy.value = true
  scrollToBottom()

  try {
    const result = await call(
      (label) => setStatus(reply, label),
      (detail) => setDetail(reply, detail),
    )
    finishSteps(reply)
    reply.threadId = result.thread_id
    if (result.status === 'needs_input' && result.kind === 'confirm_categories') {
      const goal = result.goal ? `제가 이해한 요청: ${result.goal}\n\n` : ''
      reply.text = `${goal}${TYPE_LABEL[result.asset_type]} 제작에 필요한 레퍼런스를 이렇게 나눠 봤어요.`
      reply.proposed = result.proposed_categories
    } else if (result.status === 'needs_input' && result.kind === 'select_images') {
      reply.text = `${formatResult(result)}\n\n마음에 드는 레퍼런스 이미지를 클릭해서 골라주세요. 고른 이미지로 지시서를 만들어요.`
      reply.categories = result.categories
      reply.candidates = result.candidates
      reply.rejected = result.rejected_candidates
      reply.sourceErrors = result.source_errors
      reply.selectable = true
    } else if (result.status === 'needs_input' && result.kind === 'confirm_brief') {
      reply.text = '지시서에 이런 내용을 쓰려고 해요. 확인하고 필요하면 고쳐주세요. 괜찮으면 \'이대로 작성 시작\'을 눌러주세요.'
      reply.briefPlan = { sections: result.brief_sections, autoSections: result.auto_sections }
    } else if (result.status === 'needs_input') {
      reply.text = formatQuestionIntro(result)
      reply.questions = result.questions
    } else {
      reply.text = '지시서를 만들었어요.'
      reply.output = result.output
    }
  } catch (err) {
    finishSteps(reply)
    reply.error = true
    reply.text = `오류가 발생했어요. ${err.message}`
  } finally {
    busy.value = false
    scrollToBottom()
  }
}

function onSend({ text, image, imageUrl }) {
  messages.value.push({ role: 'user', text, imageUrl })
  return runAgent((onStatus, onDetail) => sendMessage({ text, image, onStatus, onDetail }))
}

// 질문 폼에서 답을 보내면 사용자 말풍선으로 남기고, 같은 작업을 이어서 실행한다
// 카테고리 확인 폼에서 확정하면 사용자 말풍선으로 남기고, 확정한 카테고리로 이미지 검색을 이어서 실행한다
function onConfirm({ message, categories, perCategory }) {
  messages.value.push({ role: 'user', text: `검색할 카테고리: ${categories.join(', ')}\n카테고리당 ${perCategory}개` })
  return runAgent(
    (onStatus, onDetail) =>
      sendCategories({ threadId: message.threadId, categories, perCategory, onStatus, onDetail }),
    { perCategory }, // 요청한 개수보다 적게 통과했을 때 안내하기 위해 결과 메시지에 남겨 둔다
  )
}

// 이미지를 골라 보내면 사용자 말풍선으로 남기고, 지시서 작성 계획 단계로 이어서 실행한다
function onSelect({ message, selectedIds, saveUnverified }) {
  const chosen = message.candidates.filter((c) => selectedIds.includes(c.id))
  const lines = (message.categories ?? [])
    .map((cat) => ({ name: cat.name, count: chosen.filter((c) => c.topic === cat.name).length }))
    .filter((g) => g.count)
    .map((g) => `${g.name} ${g.count}장`)
  const note = saveUnverified ? '\n라이선스를 확인하지 못한 이미지도 파일로 저장' : ''
  messages.value.push({ role: 'user', text: `선택한 이미지 ${chosen.length}장\n${lines.join(', ')}${note}` })
  return runAgent((onStatus, onDetail) =>
    sendSelection({ threadId: message.threadId, selectedIds, saveUnverified, onStatus, onDetail }),
  )
}

// 지시서 작성 계획을 승인하면 사용자 말풍선으로 남기고, 이미지 저장과 지시서 작성을 시작한다
function onBrief({ message, sections, notes }) {
  const extra = notes ? `\n추가 요청: ${notes}` : ''
  messages.value.push({ role: 'user', text: `지시서 작성 계획 확인 (섹션 ${sections.length}개)${extra}` })
  return runAgent((onStatus, onDetail) =>
    sendBrief({ threadId: message.threadId, sections, notes, onStatus, onDetail }),
  )
}

function onAnswer({ message, answers }) {
  const labels = Object.fromEntries(message.questions.map((q) => [q.key, q.label]))
  const lines = Object.entries(answers)
    .filter(([, v]) => v)
    .map(([k, v]) => (k === 'asset_type' ? TYPE_LABEL[v] : `${labels[k]}: ${v}`))
  messages.value.push({ role: 'user', text: lines.join('\n') || '(모두 미정으로 둘게요)' })
  return runAgent((onStatus, onDetail) =>
    sendAnswers({ threadId: message.threadId, answers, onStatus, onDetail }),
  )
}
</script>

<template>
  <div class="chat" :class="{ empty: isEmpty }">
    <AppHeader />

    <div v-if="!isEmpty" ref="scroller" class="scroller">
      <div class="messages">
        <ChatMessage v-for="(m, i) in messages" :key="i" :message="m" :now="now" :busy="busy"
          @answer="onAnswer" @confirm="onConfirm" @select="onSelect"
          @brief="onBrief" />
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
