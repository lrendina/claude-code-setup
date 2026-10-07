export type Forecast = {
  /** Context tokens at the end of each main-loop turn, oldest first, at most 12. */
  samples: number[]
  /** The model's context window, in tokens. */
  window: number
  /** `$.session.usage().startedAt` the samples belong to; a change means /clear. */
  startedAt: number
}

declare module 'claude-code' {
  interface PluginState {
    'token-weather': { forecast: Forecast | null }
  }
}
