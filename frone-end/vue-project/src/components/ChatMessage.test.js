import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import ChatMessage from './ChatMessage.vue'

const cand = (id, topic, license = 'confirmed', extra = {}) => ({
  id, topic, license, title: `Image ${id}`, thumbnail_url: `https://t/${id}.jpg`, source_url: `https://s/${id}`,
  image_url: `https://i/${id}.jpg`, license_detail: 'CC BY 2.0', source_name: 'Openverse', creator: 'kim',
  reason: '검색어: cloak', review: '적합함', score: 0.9, tags: [], ...extra,
})

function assistant(extra = {}) {
  return {
    role: 'assistant', text: '골라주세요', steps: [], selectable: true,
    categories: [{ name: '외피', queries: ['cloak'], applied_rules: [] }, { name: '배경', queries: ['snow'], applied_rules: [] }],
    candidates: [cand('a', '외피'), cand('b', '외피', 'unclear'), cand('c', '배경', 'restricted'), cand('d', '배경')],
    rejected: [], ...extra,
  }
}

const mountMessage = (message, props = {}) => mount(ChatMessage, { props: { message, now: Date.now(), ...props } })
const cards = (w) => w.findAll('li.card')
const makeBtn = (w) => w.find('button.make')

describe('ChatMessage - 이미지 선택', () => {
  it('이미지를 클릭하면 선택/해제되고 선택 수가 보인다', async () => {
    const w = mountMessage(assistant())
    expect(w.find('.selection-bar strong').text()).toBe('0장 선택')
    expect(makeBtn(w).attributes('disabled')).toBeDefined() // 아무것도 안 골랐으면 못 보냄

    await cards(w)[0].find('button.thumb').trigger('click')
    await cards(w)[3].find('button.thumb').trigger('click')
    expect(cards(w)[0].classes()).toContain('picked')
    expect(cards(w)[0].find('button.thumb').attributes('aria-pressed')).toBe('true')
    expect(w.find('.selection-bar strong').text()).toBe('2장 선택')
    expect(makeBtn(w).attributes('disabled')).toBeUndefined()

    await cards(w)[0].find('button.thumb').trigger('click') // 다시 누르면 해제
    expect(cards(w)[0].classes()).not.toContain('picked')
    expect(w.find('.selection-bar strong').text()).toBe('1장 선택')
  })

  it('고른 이미지 id 를 보내고, 보낸 뒤에는 선택을 바꾸거나 다시 보낼 수 없다', async () => {
    const w = mountMessage(assistant())
    await cards(w)[0].find('button.thumb').trigger('click')
    await cards(w)[3].find('button.thumb').trigger('click')
    await makeBtn(w).trigger('click')

    expect(w.emitted('select')).toHaveLength(1)
    expect(w.emitted('select')[0][0]).toMatchObject({ selectedIds: ['a', 'd'], saveUnverified: false })

    await makeBtn(w).trigger('click')
    await cards(w)[1].find('button.thumb').trigger('click')
    expect(w.emitted('select')).toHaveLength(1)
    expect(cards(w)[1].classes()).not.toContain('picked')
    expect(makeBtn(w).text()).toBe('선택을 보냈어요')
  })

  it('라이선스를 확인하지 못한 이미지를 골랐을 때만 "파일로 저장" 선택지가 나온다', async () => {
    const w = mountMessage(assistant())
    await cards(w)[0].find('button.thumb').trigger('click') // 확인된 이미지
    expect(w.find('.unverified').exists()).toBe(false)

    await cards(w)[1].find('button.thumb').trigger('click') // 확인 필요 이미지
    expect(w.find('.unverified').text()).toContain('1장도 파일로 저장')
    expect(w.find('.hint').text()).toContain('링크만 기록')

    await w.find('.unverified input').setValue(true)
    await makeBtn(w).trigger('click')
    expect(w.emitted('select')[0][0]).toMatchObject({ selectedIds: ['a', 'b'], saveUnverified: true })
  })

  it('제한된 이미지는 체크해도 저장되지 않는다고 미리 알려준다', async () => {
    const w = mountMessage(assistant())
    await cards(w)[2].find('button.thumb').trigger('click') // restricted
    expect(w.find('.unverified').exists()).toBe(false) // 저장을 허용할 수 있는 선택지 자체가 없다
    expect(w.find('.hint').text()).toContain('제한됨 1장은 파일로 저장하지 않고 링크만')
  })

  it('작업 중(busy)에는 선택할 수 없다', async () => {
    const w = mountMessage(assistant(), { busy: true })
    expect(cards(w)[0].find('button.thumb').attributes('disabled')).toBeDefined()
    expect(makeBtn(w).attributes('disabled')).toBeDefined()
  })

  it('선택 모드가 아니면 이미지가 원본 페이지 링크로 열린다', () => {
    const w = mountMessage(assistant({ selectable: false }))
    expect(w.find('.selection-bar').exists()).toBe(false)
    expect(cards(w)[0].find('button.thumb').exists()).toBe(false)
    expect(cards(w)[0].find('a').attributes('href')).toBe('https://s/a')
  })

  it('카테고리별로 묶어 보여주고 적합도와 검토 의견을 함께 보여준다', () => {
    const w = mountMessage(assistant())
    expect(w.findAll('.group h2').map((h) => h.text().replace(/\s+/g, ' '))).toEqual(['외피 2개', '배경 2개'])
    expect(cards(w)[0].text()).toContain('적합도 9/10')
    expect(cards(w)[0].text()).toContain('적합함')
  })
})

describe('ChatMessage - 계획 승인과 결과', () => {
  it('지시서 계획 폼의 제출을 brief 이벤트로 전달한다', async () => {
    const message = { role: 'assistant', text: '', steps: [], briefPlan: { sections: [{ heading: '목표', outline: 'o' }], autoSections: [] } }
    const w = mountMessage(message)
    await w.find('form').trigger('submit')
    expect(w.emitted('brief')[0][0]).toMatchObject({ sections: [{ heading: '목표', outline: 'o' }], notes: '' })
  })

  it('결과 폴더 위치와 저장 요약, 지시서 미리보기를 보여준다', () => {
    const output = { folder: 'result/artBrief_001', brief_file: '지시서.md', saved: 3, link_only: 2, failed: 1, brief_markdown: '# 작업 지시서' }
    const w = mountMessage({ role: 'assistant', text: '지시서를 만들었어요.', steps: [], output })
    const text = w.find('.output').text()
    expect(w.find('.folder').text()).toBe('result/artBrief_001/')
    expect(text).toContain('이미지 3장을 카테고리 폴더에 저장')
    expect(text).toContain('2장은 라이선스를 확인하지 못했거나 제한되어 링크만')
    expect(text).toContain('1장은 내려받지 못해')
    expect(w.find('.preview pre').text()).toBe('# 작업 지시서')
  })

  it('링크만/실패가 없으면 해당 안내를 보이지 않는다', () => {
    const output = { folder: 'result/artBrief_002', brief_file: '지시서.md', saved: 2, link_only: 0, failed: 0, brief_markdown: '#' }
    const w = mountMessage({ role: 'assistant', text: '', steps: [], output })
    expect(w.find('.output').text()).not.toContain('링크만')
    expect(w.find('.output .fail').exists()).toBe(false)
  })
})
