<script setup>
import { computed, ref, watch, nextTick } from 'vue'

const props = defineProps({
  disabled: { type: Boolean, default: false },
})
const emit = defineEmits(['send'])

const text = ref('')
const file = ref(null)
const previewUrl = ref('')
const textarea = ref(null)
const fileInput = ref(null)

// 현재 서버(/upload)가 이미지와 텍스트를 모두 요구한다.
const canSend = computed(() => !props.disabled && text.value.trim() && file.value)

function onFile(e) {
  const picked = e.target.files[0]
  if (!picked) return
  file.value = picked
  previewUrl.value = URL.createObjectURL(picked)
}

function removeFile() {
  file.value = null
  previewUrl.value = ''
  if (fileInput.value) fileInput.value.value = ''
}

function send() {
  if (!canSend.value) return
  emit('send', { text: text.value.trim(), image: file.value, imageUrl: previewUrl.value })
  text.value = ''
  file.value = null
  previewUrl.value = '' // 미리보기 URL 은 메시지가 이어서 사용한다
  if (fileInput.value) fileInput.value.value = ''
}

function onKeydown(e) {
  // 한글 조합 중 Enter 는 전송하지 않는다
  if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
    e.preventDefault()
    send()
  }
}

// 입력 길이에 맞춰 높이를 늘린다
watch(text, async () => {
  await nextTick()
  const el = textarea.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = `${Math.min(el.scrollHeight, 200)}px`
})
</script>

<template>
  <form class="composer" @submit.prevent="send">
    <div v-if="previewUrl" class="preview">
      <img :src="previewUrl" alt="첨부할 이미지 미리보기" />
      <button type="button" class="remove" aria-label="이미지 제거" @click="removeFile">×</button>
    </div>

    <textarea
      ref="textarea"
      v-model="text"
      rows="1"
      placeholder="만들고 싶은 대상이나 분위기를 설명해주세요"
      @keydown="onKeydown"
    ></textarea>

    <div class="actions">
      <input ref="fileInput" type="file" accept="image/*" hidden @change="onFile" />
      <button type="button" class="icon-btn" aria-label="이미지 첨부" :disabled="disabled"
        @click="fileInput.click()">
        <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor"
          stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <rect x="3" y="4" width="18" height="16" rx="3" />
          <circle cx="9" cy="10" r="1.6" />
          <path d="m4 18 5-5 4 4 3-3 4 4" />
        </svg>
      </button>

      <span class="hint">{{ file ? '' : '이미지를 함께 첨부해주세요' }}</span>

      <button type="submit" class="send" aria-label="전송" :disabled="!canSend">
        <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor"
          stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <path d="M12 19V5M5 12l7-7 7 7" />
        </svg>
      </button>
    </div>
  </form>
</template>

<style scoped>
.composer {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 22px;
  padding: 12px 14px 10px;
  display: grid;
  gap: 8px;
}

.composer:focus-within {
  border-color: var(--accent);
}

textarea {
  width: 100%;
  resize: none;
  border: 0;
  background: transparent;
  outline: none;
  line-height: 1.6;
  max-height: 200px;
}

textarea::placeholder {
  color: var(--text-muted);
}

.preview {
  position: relative;
  width: 72px;
  height: 72px;
}

.preview img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  border-radius: 10px;
  border: 1px solid var(--border);
}

.remove {
  position: absolute;
  top: -6px;
  right: -6px;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  border: 0;
  background: var(--text);
  color: var(--bg);
  line-height: 1;
  font-size: 14px;
  padding: 0;
}

.actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.hint {
  flex: 1;
  font-size: 13px;
  color: var(--text-muted);
}

.icon-btn,
.send {
  display: grid;
  place-items: center;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  border: 0;
  background: transparent;
  color: var(--text-muted);
}

.icon-btn:hover:not(:disabled) {
  background: color-mix(in srgb, var(--text) 8%, transparent);
  color: var(--text);
}

.send {
  background: var(--accent-strong);
  color: var(--bg);
}

.send:disabled {
  background: color-mix(in srgb, var(--text) 14%, transparent);
  color: var(--text-muted);
  cursor: not-allowed;
}

.icon-btn:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}
</style>
