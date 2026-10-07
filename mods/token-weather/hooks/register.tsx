import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { Forecast } from '../types'
import { fmtDelta, fmtTokens, percentOf, push, sparkline, weather } from './forecast'

const forecast = atom({ plugin: 'token-weather', key: 'forecast' } as const, null)

// Records the live context fill as one sample. A reading with no tokens
// (fresh or just-compacted window) records nothing: the last good value stays.
const sample = async ($: EngineInterface) => {
  const { startedAt, context } = await $.session.usage()
  const tokens = context.tokens

  if (tokens === undefined) {
    return
  }

  await update($, forecast, (prev: Forecast | null): Forecast => {
    const samples = prev && prev.startedAt === startedAt ? prev.samples : []

    return { samples: push(samples, tokens), window: context.window, startedAt }
  })
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    const result = await next(e)
    const prev = await read($, forecast)

    // A resumed session gets a baseline so its first turn's delta is real;
    // a hot reload keeps what $.state already has.
    if (prev === null) {
      await sample($)
    }

    return result
  })

  on('turn.complete', async ($, e, next) => {
    const result = await next(e)

    if (e.agentId === undefined) {
      await sample($)
    }

    return result
  })

  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    const f = await read($, forecast)
    const tokens = f?.samples.at(-1)

    if (e.props.hasSurvey || f === null || tokens === undefined) {
      return next(e)
    }

    const { Box, Text } = $.ui.resolve(e)
    const percent = percentOf(tokens, f.window)
    const sky = weather(percent)
    const previous = f.samples.at(-2)

    return (
      <Box>
        <Text color={sky.color} bold>
          {sky.icon} {sky.word}
        </Text>
        <Text>
          {'  '}
          {percent}% · {fmtTokens(tokens)} / {fmtTokens(f.window)}
        </Text>
        <Text color={sky.color}>
          {'  '}
          {sparkline(f.samples, f.window)}
        </Text>
        {previous !== undefined && (
          <Text dimColor>
            {'  '}
            {fmtDelta(tokens - previous)} last turn
          </Text>
        )}
      </Box>
    )
  })
}
