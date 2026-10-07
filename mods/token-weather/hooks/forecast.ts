export const HISTORY = 12

const BARS = ['▁', '▂', '▃', '▄', '▅', '▆', '▇', '█'] as const

export type Weather = { icon: string; word: string; color: string }

export const weather = (percent: number): Weather => {
  if (percent < 25) return { icon: '☀', word: 'Clear', color: 'yellow' }
  if (percent < 50) return { icon: '☁', word: 'Cloudy', color: 'cyan' }
  if (percent < 75) return { icon: '☂', word: 'Showers', color: 'blue' }
  if (percent < 90) return { icon: '☇', word: 'Storm', color: 'magenta' }
  return { icon: '↯', word: 'Compact soon', color: 'red' }
}

// Bar height is the share of the window, so it means what the icon means.
export const sparkline = (samples: readonly number[], window: number): string =>
  samples
    .map(t => BARS[Math.max(0, Math.min(7, Math.floor((t / window) * 8)))] ?? '█')
    .join('')

const trim = (n: number): string => (Number.isInteger(n) ? String(n) : n.toFixed(1))

export const fmtTokens = (n: number): string => {
  if (n >= 1_000_000) return `${trim(Math.round(n / 100_000) / 10)}M`
  if (n >= 1_000) return `${trim(Math.round(n / 100) / 10)}k`
  return String(n)
}

export const fmtDelta = (n: number): string =>
  n < 0 ? `▼ −${fmtTokens(-n)}` : `▲ +${fmtTokens(n)}`

export const percentOf = (tokens: number, window: number): number =>
  Math.round((tokens / window) * 100)

export const push = (samples: readonly number[], tokens: number): number[] =>
  [...samples, tokens].slice(-HISTORY)
