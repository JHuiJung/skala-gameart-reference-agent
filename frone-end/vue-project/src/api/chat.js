const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

async function parse(res) {
  const json = await res.json()
  if (!res.ok) {
    const detail = typeof json.detail === 'string' ? json.detail : JSON.stringify(json.detail)
    throw new Error(detail)
  }
  return json
}

/**
 * 텍스트 + 이미지로 새 작업을 시작한다.
 *
 * 응답의 status 가 'needs_input' 이면 questions 에 답해야 할 질문이 있고(→ sendAnswers),
 * 'done' 이면 처리 결과가 들어 있다.
 *
 * onStatus(label) 은 "지금 하고 있는 일"이 바뀔 때마다 호출된다.
 * 지금은 서버가 단계를 알려주지 않아 전송/대기 두 단계만 알 수 있다.
 * 에이전트가 단계를 스트리밍하면 여기서 onStatus 로 넘기면 된다.
 */
export async function sendMessage({ text, image, onStatus }) {
  const form = new FormData()
  form.append('text', text)
  form.append('image', image)

  onStatus('서버로 전송 중')
  const request = fetch(`${API_URL}/upload`, { method: 'POST', body: form })
  onStatus('서버 응답 대기 중')
  return parse(await request)
}

/** 에이전트의 질문에 대한 답을 보내 멈춘 작업을 이어서 실행한다. answers: { 질문 key: 답 } */
export async function sendAnswers({ threadId, answers, onStatus }) {
  onStatus('답변 전송 중')
  const request = fetch(`${API_URL}/answer`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ thread_id: threadId, answers }),
  })
  onStatus('서버 응답 대기 중')
  return parse(await request)
}

/** 사용자가 확정한 레퍼런스 카테고리 이름들을 보내 이미지 검색을 이어서 실행한다. */
export async function sendCategories({ threadId, categories, onStatus }) {
  onStatus('카테고리 전송 중')
  const request = fetch(`${API_URL}/answer`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ thread_id: threadId, categories }),
  })
  onStatus('서버 응답 대기 중')
  return parse(await request)
}
