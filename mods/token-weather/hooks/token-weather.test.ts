import { describe, expect, test } from 'claude-code/testing'
import type { On, RenderElement, SessionUsage } from 'claude-code'

import { fmtDelta, fmtTokens, push, sparkline, weather } from './forecast'

describe('forecast', () => {
  test('bands switch at 25, 50, 75 and 90', () => {
    const words = [0, 24, 25, 49, 50, 74, 75, 89, 90, 100].map(p => weather(p).word)
    expect(words).toEqual([
      'Clear', 'Clear', 'Cloudy', 'Cloudy', 'Showers',
      'Showers', 'Storm', 'Storm', 'Compact soon', 'Compact soon',
    ])
    expect(weather(10).color).toBe('yellow')
    expect(weather(95).icon).toBe('↯')
  })

  test('tokens format as k and M', () => {
    expect(fmtTokens(134_400)).toBe('134.4k')
    expect(fmtTokens(200_000)).toBe('200k')
    expect(fmtTokens(1_000_000)).toBe('1M')
    expect(fmtTokens(850)).toBe('850')
    expect(fmtTokens(0)).toBe('0')
  })

  test('deltas point up or down', () => {
    expect(fmtDelta(98_300)).toBe('▲ +98.3k')
    expect(fmtDelta(-120_000)).toBe('▼ −120k')
    expect(fmtDelta(0)).toBe('▲ +0')
  })

  test('history keeps the last 12 turns', () => {
    let samples: number[] = []
    for (let t = 1; t <= 13; t++) samples = push(samples, t)
    expect(samples).toEqual([2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13])
  })

  test('sparkline scales to the window', () => {
    expect(sparkline([0, 100_000, 199_999, 200_000, 250_000], 200_000)).toBe('▁▅███')
  })
})

const answer = (on: On, readings: (number | undefined)[], startedAt = 1) => {
  let i = 0
  on('session.usage', () => {
    const tokens = readings[Math.min(i++, readings.length - 1)]
    const value: SessionUsage = { startedAt, context: { tokens, window: 200_000 }, rateLimits: [] }
    return { value }
  })
  on('session.start', ($, e) => ({ cwd: e.cwd }))
  on('turn.complete', () => ({ text: '' }))
  on('ui.render', ($, e) => {
    const { Text } = $.ui.resolve(e)
    return h(Text, {}, 'engine band') as RenderElement
  })
}

const line = async (ui: { findAll: (q: { type: string }) => Promise<{ text: string; props: Record<string, unknown> }[]> }) => {
  const texts = await ui.findAll({ type: 'Text' })
  return { text: texts.map(t => t.text).join(''), first: texts[0] }
}

const turn = { answer: 'ok', durationMs: 1, isAborted: false, turnId: 't', reason: 'answer' } as const

const band = {
  hasSurvey: false,
  isWorking: false,
  maxRows: 10,
  bodyColumns: 120,
} as never

for (const surface of ['terminal', 'desktop'] as const) {
  describe(surface, () => {
    test('draws the forecast after each turn', async ($, on) => {
      answer(on, [36_100, 134_400])
      await $.session.start({ cwd: '/', surface, isInteractive: true })
      await $.turn.complete(turn)

      const ui = await $.ui.mount({ plugin: 'token-weather', surface, component: 'AbovePrompt', props: band })
      const { text, first } = await line(ui)
      expect(text).toBe('☂ Showers  67% · 134.4k / 200k  ▂▆  ▲ +98.3k last turn')
      expect(first?.props.color).toBe('blue')
    })

    test('a reading without tokens keeps the last good value', async ($, on) => {
      answer(on, [50_000, undefined])
      await $.session.start({ cwd: '/', surface, isInteractive: true })
      await $.turn.complete(turn)

      const ui = await $.ui.mount({ plugin: 'token-weather', surface, component: 'AbovePrompt', props: band })
      expect((await line(ui)).text).toBe('☁ Cloudy  25% · 50k / 200k  ▃')
    })

    test('a turn after compaction shows the drop', async ($, on) => {
      answer(on, [180_000, 30_000])
      await $.session.start({ cwd: '/', surface, isInteractive: true })
      await $.turn.complete(turn)

      const ui = await $.ui.mount({ plugin: 'token-weather', surface, component: 'AbovePrompt', props: band })
      expect((await line(ui)).text).toBe('☀ Clear  15% · 30k / 200k  █▂  ▼ −150k last turn')
    })

    test('/clear starts the chart over', async ($, on) => {
      let startedAt = 1
      const readings = [60_000, 120_000, 20_000]
      let i = 0
      on('session.usage', () => {
        const value: SessionUsage = { startedAt, context: { tokens: readings[i++], window: 200_000 }, rateLimits: [] }
        return { value }
      })
      on('session.start', ($, e) => ({ cwd: e.cwd }))
      on('turn.complete', () => ({ text: '' }))
      await $.session.start({ cwd: '/', surface, isInteractive: true })
      await $.turn.complete(turn)
      startedAt = 2
      await $.turn.complete(turn)

      const ui = await $.ui.mount({ plugin: 'token-weather', surface, component: 'AbovePrompt', props: band })
      expect((await line(ui)).text).toBe('☀ Clear  10% · 20k / 200k  ▁')
    })

    test('a survey takes the band', async ($, on) => {
      answer(on, [100_000])
      await $.session.start({ cwd: '/', surface, isInteractive: true })

      const props = { hasSurvey: true, isWorking: false, maxRows: 10, bodyColumns: 120 } as never
      const ui = await $.ui.mount({ plugin: 'token-weather', surface, component: 'AbovePrompt', props })
      expect((await line(ui)).text).toBe('engine band')
    })

    test('subagent turns are ignored', async ($, on) => {
      answer(on, [undefined, 80_000])
      await $.session.start({ cwd: '/', surface, isInteractive: true })
      await $.turn.complete({ ...turn, agentId: 'sub' })

      const ui = await $.ui.mount({ plugin: 'token-weather', surface, component: 'AbovePrompt', props: band })
      expect((await line(ui)).text).toBe('engine band')
    })
  })
}
