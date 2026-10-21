<script setup>
import { reactive, ref } from 'vue'

// 에이전트가 되묻는 질문 폼.
// questions: [{ key, label, question, hint, options: [{ value, label }] }]
// 선택지(options)가 있으면 버튼으로, 없으면 입력칸으로 답한다. 비워 둔 항목은 서버에서 '미정'으로 처리된다.
const props = defineProps({
  questions: { type: Array, required: true },
  disabled: { type: Boolean, default: false },
})
const emit = defineEmits(['submit'])

const answers = reactive(Object.fromEntries(props.questions.map((q) => [q.key, ''])))
const submitted = ref(false)

function submit(values = answers) {
  if (submitted.value || props.disabled) return
  submitted.value = true
  emit('submit', { ...values })
}
</script>

<template>
  <form class="questions" @submit.prevent="submit()">
    <div v-for="q in questions" :key="q.key" class="question">
      <label :for="`q-${q.key}`">{{ q.question }}</label>

      <div v-if="q.options.length" class="options">
        <button v-for="o in q.options" :key="o.value" type="button" class="option"
          :disabled="submitted || disabled" @click="submit({ [q.key]: o.value })">
          {{ o.label }}
        </button>
      </div>

      <textarea v-else :id="`q-${q.key}`" v-model="answers[q.key]" rows="2" :placeholder="q.hint"
        :disabled="submitted || disabled"></textarea>
    </div>

    <div v-if="!questions[0].options.length" class="footer">
      <span class="note">{{ submitted ? '답변을 보냈어요' : '비워 두면 미정으로 두고 AI가 제안해요' }}</span>
      <button type="submit" class="submit" :disabled="submitted || disabled">답변 보내기</button>
    </div>
  </form>
</template>

<style scoped>
.questions {
  display: grid;
  gap: 14px;
  padding: 14px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
}

.question {
  display: grid;
  gap: 6px;
}

label {
  font-weight: 600;
}

textarea {
  width: 100%;
  resize: vertical;
  padding: 8px 10px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--bg);
  outline: none;
}

textarea:focus {
  border-color: var(--accent);
}

textarea:disabled {
  opacity: 0.6;
}

.options {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.option {
  padding: 8px 16px;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: var(--bg);
}

.option:hover:not(:disabled) {
  border-color: var(--accent);
}

.option:disabled,
.submit:disabled {
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

.submit {
  padding: 8px 18px;
  border: 0;
  border-radius: 999px;
  background: var(--accent-strong);
  color: var(--bg);
  font-weight: 600;
}
</style>
