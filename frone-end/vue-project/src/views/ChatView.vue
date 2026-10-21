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

async function onSend({ text, image, imageUrl }) {
  messages.value.push({ role: 'user', text, imageUrl })
  messages.value.push({ role: 'assistant', text: '', steps: [] })
  const reply = messages.value[messages.value.length - 1]
  busy.value = true
  scrollToBottom()

  try {
    const result = await sendMessage({ text, image, onStatus: (label) => setStatus(reply, label) })
    finishSteps(reply)
    reply.text = `${result.message}: ${result.image_name} (${result.image_size} bytes)`
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
