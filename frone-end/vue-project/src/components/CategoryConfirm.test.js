import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import CategoryConfirm from './CategoryConfirm.vue'

const categories = [
  { name: '겨울 외피', reason: '방한', applied_rules: ['중세 후기 복식 기준'] },
  { name: '겨울 배경', reason: '서식지', applied_rules: [] },
  { name: '색감', reason: '분위기', applied_rules: [] },
]
const mountForm = (props = {}) => mount(CategoryConfirm, { props: { categories, ...props } })

describe('CategoryConfirm', () => {
  it('제안된 카테고리를 모두 선택한 상태로 보여주고, 반영한 세계관 규칙도 보여준다', () => {
    const w = mountForm()
    expect(w.find('.summary').text()).toContain('3개 카테고리 [겨울 외피, 겨울 배경, 색감]')
    expect(w.find('.rule').text()).toContain('중세 후기 복식 기준')
  })

  it('체크를 해제해 빼고 직접 추가한 카테고리와 이미지 수를 보낸다', async () => {
    const w = mountForm()
    await w.findAll('li input[type=checkbox]')[2].setValue(false) // 색감 제외
    await w.find('.add input').setValue('눈 덮인 가로등')
    await w.find('.add button').trigger('click')
    await w.find('#per-category').setValue(7)
    await w.find('form').trigger('submit')

    expect(w.emitted('submit')[0][0]).toEqual({ categories: ['겨울 외피', '겨울 배경', '눈 덮인 가로등'], perCategory: 7 })
  })

  it('이미지 수의 기본값은 5이고 1~10 범위로 고르게 한다', () => {
    const slider = mountForm().find('#per-category')
    expect(slider.element.value).toBe('5')
    expect([slider.attributes('min'), slider.attributes('max')]).toEqual(['1', '10'])
  })

  it('카테고리를 모두 빼면 보낼 수 없고, 같은 이름은 추가되지 않는다', async () => {
    const w = mountForm()
    for (const box of w.findAll('li input[type=checkbox]')) await box.setValue(false)
    expect(w.find('button.submit').attributes('disabled')).toBeDefined()

    await w.findAll('li input[type=checkbox]')[0].setValue(true)
    await w.find('.add input').setValue('겨울 외피') // 이미 있는 이름
    await w.find('.add button').trigger('click')
    expect(w.findAll('li.added')).toHaveLength(0)
  })

  it('카테고리는 최대 8개까지만 추가할 수 있다', async () => {
    const w = mountForm()
    for (let i = 0; i < 10; i++) {
      await w.find('.add input').setValue(`추가${i}`)
      await w.find('.add button').trigger('click')
    }
    expect(w.findAll('li.added')).toHaveLength(5) // 제안 3개 + 추가 5개 = 8개
    expect(w.find('.add input').attributes('disabled')).toBeDefined()
  })

  it('보낸 뒤에는 잠긴다', async () => {
    const w = mountForm()
    await w.find('form').trigger('submit')
    await w.find('form').trigger('submit')
    expect(w.emitted('submit')).toHaveLength(1)
  })
})
