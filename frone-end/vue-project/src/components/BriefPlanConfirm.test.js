import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import BriefPlanConfirm from './BriefPlanConfirm.vue'

const sections = [
  { heading: '작업 목적', outline: '목표를 적는다' },
  { heading: '색상 가이드', outline: '최대 5색' },
  { heading: '검토 체크리스트', outline: '확인 항목' },
]
const AUTO = ['참고 이미지별 설명과 활용 목적', '이미지 출처 및 라이선스 확인 정보']

function mountForm(props = {}) {
  return mount(BriefPlanConfirm, { props: { sections, autoSections: AUTO, ...props } })
}
const headings = (w) => w.findAll('.head input').map((i) => i.element.value)
const submitBtn = (w) => w.find('button.submit')

describe('BriefPlanConfirm', () => {
  it('AI 가 세운 계획을 섹션별로 보여주고 자동 작성 섹션은 수정할 수 없게 따로 알려준다', () => {
    const w = mountForm()
    expect(headings(w)).toEqual(['작업 목적', '색상 가이드', '검토 체크리스트'])
    expect(w.findAll('textarea').slice(0, 3).map((t) => t.element.value)).toEqual(['목표를 적는다', '최대 5색', '확인 항목'])
    expect(w.find('.auto').text()).toContain('참고 이미지별 설명과 활용 목적')
    expect(submitBtn(w).attributes('disabled')).toBeUndefined()
  })

  it('수정한 제목·내용(앞뒤 공백 제거)과 추가 요청을 그대로 보낸다', async () => {
    const w = mountForm()
    await w.findAll('.head input')[0].setValue('  작업 목적 및 목표  ')
    await w.findAll('textarea')[0].setValue('  사용자가 고친 내용  ')
    await w.find('#brief-notes').setValue(' 쉬운 말로 써주세요 ')
    await w.find('form').trigger('submit')

    const [[payload]] = w.emitted('submit')
    expect(payload.sections[0]).toEqual({ heading: '작업 목적 및 목표', outline: '사용자가 고친 내용' })
    expect(payload.sections).toHaveLength(3)
    expect(payload.notes).toBe('쉬운 말로 써주세요')
  })

  it('섹션을 지우고 순서를 바꿀 수 있고, 첫/마지막 섹션은 더 못 움직인다', async () => {
    const w = mountForm()
    const [up0, down0] = w.findAll('.head')[0].findAll('button.icon')
    expect(up0.attributes('disabled')).toBeDefined()
    expect(w.findAll('.head')[2].findAll('button.icon')[1].attributes('disabled')).toBeDefined()

    await down0.trigger('click') // 첫 섹션을 아래로
    expect(headings(w)).toEqual(['색상 가이드', '작업 목적', '검토 체크리스트'])

    await w.findAll('.head')[1].findAll('button.icon')[2].trigger('click') // '작업 목적' 삭제
    expect(headings(w)).toEqual(['색상 가이드', '검토 체크리스트'])

    await w.find('form').trigger('submit')
    expect(w.emitted('submit')[0][0].sections.map((s) => s.heading)).toEqual(['색상 가이드', '검토 체크리스트'])
  })

  it('마지막 한 섹션은 지울 수 없다', async () => {
    const w = mountForm({ sections: [sections[0]] })
    expect(w.find('.head button[aria-label="섹션 삭제"]').attributes('disabled')).toBeDefined()
  })

  it('새 섹션을 추가할 수 있지만 제목을 채우기 전에는 보낼 수 없다', async () => {
    const w = mountForm()
    await w.find('button.add').trigger('click')
    expect(headings(w)).toHaveLength(4)
    expect(submitBtn(w).attributes('disabled')).toBeDefined()
    expect(w.find('.note').text()).toContain('제목이 비어 있는')

    await w.findAll('.head input')[3].setValue('표정·포즈')
    expect(submitBtn(w).attributes('disabled')).toBeUndefined()
  })

  it('제목이 겹치거나 자동 작성 섹션과 같으면 보낼 수 없다', async () => {
    const w = mountForm()
    await w.findAll('.head input')[1].setValue('작업 목적')
    expect(submitBtn(w).attributes('disabled')).toBeDefined()
    expect(w.find('.note').text()).toContain('제목이 같은')

    await w.findAll('.head input')[1].setValue(AUTO[1])
    expect(w.find('.note').text()).toContain('자동으로 작성되는')
    expect(submitBtn(w).attributes('disabled')).toBeDefined()
  })

  it('섹션은 15개까지만 추가할 수 있다', async () => {
    const w = mountForm()
    for (let i = 0; i < 20; i++) await w.find('button.add').trigger('click')
    expect(headings(w)).toHaveLength(15)
    expect(w.find('button.add').attributes('disabled')).toBeDefined()
  })

  it('한 번 보내면 잠기고 다시 보낼 수 없다', async () => {
    const w = mountForm()
    await w.find('form').trigger('submit')
    await w.find('form').trigger('submit')
    expect(w.emitted('submit')).toHaveLength(1)
    expect(submitBtn(w).attributes('disabled')).toBeDefined()
    expect(w.find('.head input').attributes('disabled')).toBeDefined()
  })
})
