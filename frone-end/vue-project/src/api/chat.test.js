import { afterEach, describe, expect, it, vi } from 'vitest'
import { sendBrief, sendCategories, sendMessage, sendSelection } from './chat'

const enc = new TextEncoder()
const sse = (event, data) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`

// 바이트를 size 개씩 잘라 보낸다. 한글(3바이트)과 이벤트 경계가 중간에서 잘리는 상황을 만든다
function streamOf(text, size) {
  const bytes = enc.encode(text)
  let i = 0
  return new ReadableStream({
    pull(controller) {
      if (i >= bytes.length) return controller.close()
      controller.enqueue(bytes.slice(i, i + size))
      i += size
    },
  })
}

function mockFetch(body, init = { status: 200 }) {
  const fetchMock = vi.fn(() => Promise.resolve(new Response(body, init)))
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

const handlers = () => {
  const logs = []
  return { logs, onStatus: (x) => logs.push(['status', x]), onDetail: (x) => logs.push(['detail', x]) }
}

afterEach(() => vi.unstubAllGlobals())

describe('SSE 해석', () => {
  const body =
    sse('step', { label: '입력 분석' }) +
    sse('detail', { detail: "'겨울 외피' 검색 완료 (1/5)" }) +
    sse('result', { status: 'done', note: '한글 데이터 😀' })

  it.each([1, 2, 3, 7, 1000])('청크를 %i바이트씩 받아도 이벤트와 한글을 올바르게 해석한다', async (size) => {
    mockFetch(streamOf(body, size))
    const h = handlers()
    const result = await sendMessage({ text: 't', image: new Blob(['x']), ...h })

    expect(h.logs).toEqual([['status', '서버에 연결 중'], ['status', '입력 분석'], ['detail', "'겨울 외피' 검색 완료 (1/5)"]])
    expect(result.note).toBe('한글 데이터 😀')
  })

  it('error 이벤트는 예외로 전달된다', async () => {
    mockFetch(streamOf(sse('error', { message: '서버에서 오류가 발생했어요 (TimeoutError)' }), 9))
    await expect(sendMessage({ text: 't', image: new Blob(['x']), ...handlers() })).rejects.toThrow('TimeoutError')
  })

  it('result 없이 스트림이 끝나면 연결이 끊긴 것으로 본다', async () => {
    mockFetch(streamOf(sse('step', { label: 'a' }), 9))
    await expect(sendMessage({ text: 't', image: new Blob(['x']), ...handlers() })).rejects.toThrow('연결이 끊겼어요')
  })

  it('스트림 시작 전에 거절되면(415 등) 서버 메시지를 그대로 보여준다', async () => {
    mockFetch(JSON.stringify({ detail: '이미지 파일만 업로드할 수 있습니다.' }), { status: 415 })
    await expect(sendMessage({ text: 't', image: new Blob(['x']), ...handlers() })).rejects.toThrow('이미지 파일만')
  })
})

describe('요청 형식 (서버 규격과 같아야 한다)', () => {
  async function bodyOf(call) {
    const fetchMock = mockFetch(streamOf(sse('result', { status: 'done' }), 50))
    await call(handlers())
    const [url, init] = fetchMock.mock.calls[0]
    return { url, body: JSON.parse(init.body) }
  }

  it('카테고리 확정', async () => {
    const r = await bodyOf((h) => sendCategories({ threadId: 't1', categories: ['a'], perCategory: 7, ...h }))
    expect(r).toEqual({ url: 'http://localhost:8000/answer/stream', body: { thread_id: 't1', categories: ['a'], per_category: 7 } })
  })

  it('이미지 선택', async () => {
    const r = await bodyOf((h) => sendSelection({ threadId: 't1', selectedIds: ['x', 'y'], saveUnverified: true, ...h }))
    expect(r.body).toEqual({ thread_id: 't1', selected_ids: ['x', 'y'], save_unverified: true })
  })

  it('지시서 계획 승인', async () => {
    const sections = [{ heading: '목표', outline: '내용' }]
    const r = await bodyOf((h) => sendBrief({ threadId: 't1', sections, notes: '쉽게', ...h }))
    expect(r.body).toEqual({ thread_id: 't1', brief_sections: sections, brief_notes: '쉽게' })
  })
})
