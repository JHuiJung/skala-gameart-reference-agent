const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

/**
 * 서버가 보내는 Server-Sent Events 를 읽는다.
 * POST 요청이라 EventSource 를 쓸 수 없어서 fetch 의 스트림으로 직접 해석한다.
 *
 * 이벤트: step(작업 단계 시작) / detail(단계 안의 세부 진행) / result(최종 응답) / error(실패)
 * 최종 응답의 status 가 'needs_input' 이면 서버가 사용자의 답을 기다리는 중이다.
 */
async function readEvents(res, { onStatus, onDetail }) {
  if (!res.ok) {
    // 스트림을 시작하기 전에 거절된 경우(잘못된 요청 등)는 일반 JSON 오류로 온다
    const json = await res.json().catch(() => ({}))
    const detail = typeof json.detail === 'string' ? json.detail : JSON.stringify(json.detail ?? res.statusText)
    throw new Error(detail)
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let result = null

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    let end
    while ((end = buffer.indexOf('\n\n')) !== -1) {
      const block = buffer.slice(0, end)
      buffer = buffer.slice(end + 2)

      const fields = Object.fromEntries(block.split('\n').map((line) => [line.slice(0, line.indexOf(': ')), line.slice(line.indexOf(': ') + 2)]))
      const data = JSON.parse(fields.data)
      if (fields.event === 'step') onStatus(data.label)
      else if (fields.event === 'detail') onDetail(data.detail)
      else if (fields.event === 'result') result = data
      else if (fields.event === 'error') throw new Error(data.message)
    }
  }

  if (!result) throw new Error('서버와의 연결이 끊겼어요.')
  return result
}

/**
 * 텍스트 + 이미지로 새 작업을 시작한다.
 * onStatus(label): 서버가 새 단계를 시작할 때, onDetail(text): 단계 안의 세부 진행이 있을 때 호출된다.
 */
export async function sendMessage({ text, image, onStatus, onDetail }) {
  const form = new FormData()
  form.append('text', text)
  form.append('image', image)

  onStatus('서버에 연결 중')
  const res = await fetch(`${API_URL}/upload/stream`, { method: 'POST', body: form })
  return readEvents(res, { onStatus, onDetail })
}

async function postJson(path, body, handlers) {
  handlers.onStatus('서버에 연결 중')
  const res = await fetch(`${API_URL}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return readEvents(res, handlers)
}

/** 에이전트의 질문에 대한 답을 보내 멈춘 작업을 이어서 실행한다. answers: { 질문 key: 답 } */
export function sendAnswers({ threadId, answers, onStatus, onDetail }) {
  return postJson('/answer/stream', { thread_id: threadId, answers }, { onStatus, onDetail })
}

/** 사용자가 확정한 레퍼런스 카테고리 이름들과 카테고리당 이미지 수(1~10)를 보내 이미지 검색을 이어서 실행한다. */
export function sendCategories({ threadId, categories, perCategory, onStatus, onDetail }) {
  return postJson(
    '/answer/stream',
    { thread_id: threadId, categories, per_category: perCategory },
    { onStatus, onDetail },
  )
}
