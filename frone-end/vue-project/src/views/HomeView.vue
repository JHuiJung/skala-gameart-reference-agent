<script setup>
import { ref } from 'vue'

const file = ref(null)
const result = ref('')

function onFile(e) {
  file.value = e.target.files[0]
}

async function submit() {
  if (!file.value) return
  const form = new FormData()
  form.append('image', file.value)

  try {
    const res = await fetch('http://localhost:8000/upload', { method: 'POST', body: form })
    const json = await res.json()
    result.value = `${json.message}: ${json.filename} (${json.size} bytes)`
  } catch (err) {
    result.value = `업로드 실패: ${err.message}`
  }
}
</script>

<template>
  <main>
    <input type="file" accept="image/*" @change="onFile" />
    <button @click="submit">업로드</button>
    <p>{{ result }}</p>
  </main>
</template>
