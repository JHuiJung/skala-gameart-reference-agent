const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

/**
 * 텍스트 + 이미지를 서버로 보낸다.
 *
 * onStatus(label) 은 "지금 하고 있는 일"이 바뀔 때마다 호출된다.
 * 지금은 서버가 단계를 알려주지 않아 전송/대기 두 단계만 알 수 있다.
 * 에이전트가 붙으면 서버가 보내는 단계 이벤트(SSE 등)를 여기서 onStatus 로 넘기면 된다.
 */
export async function sendMessage({ text, image, onStatus }) {
  const form = new FormData()
  form.append('text', text)
  form.append('image', image)

  onStatus('서버로 전송 중')
  const request = fetch(`${API_URL}/upload`, { method: 'POST', body: form })
  onStatus('서버 응답 대기 중')

  const res = await request
  const json = await res.json()
  if (!res.ok) {
    const detail = typeof json.detail === 'string' ? json.detail : JSON.stringify(json.detail)
    throw new Error(detail)
  }
  return json
}
