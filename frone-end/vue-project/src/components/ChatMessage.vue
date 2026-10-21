<script setup>
import AgentStatus from './AgentStatus.vue'

// message: { role: 'user' | 'assistant', text, imageUrl?, steps?, error? }
defineProps({
  message: { type: Object, required: true },
  now: { type: Number, required: true },
})
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
</style>
