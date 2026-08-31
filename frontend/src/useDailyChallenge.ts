import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { MissedDistrict, Pin, Reveal } from './MapView'
import { activeLanguage } from './i18n'
import i18n from './i18n'
import { apiErrorMessage, apiFetch } from './api'
import { track } from './analytics'

export type District = {
  id: number
  name: string
}

type AccountIdentity = {
  username: string
}

type ChallengeResponse = {
  generation_version: string
  date?: string
  seed?: string
  pins: Pin[]
  initial_budget: number
  budget_remaining: number
  solved_pins: Reveal[]
  missed_districts: MissedDistrict[]
  guess_history: ApiGuessHistoryEntry[]
  status: 'in_progress' | 'finished'
  state_source: 'anonymous' | 'account'
  finish_reason?: 'solved' | 'budget' | 'gave_up' | null
}

export type Challenge = ChallengeResponse & {
  mode: 'daily' | 'seeded'
  id: string
}

type GuessResult = {
  correct: boolean
  solved_pin_index: number | null
  distance_km: number | null
  missed_district: MissedDistrict | null
  budget_remaining: number
  status: 'in_progress' | 'finished'
  reveals: Reveal[]
}

type GiveUpResult = {
  budget_remaining: number
  status: 'finished'
  reveals: Reveal[]
}

export type LeaderboardEntry = {
  rank: number
  username: string
  pins_solved: number
  guesses_used: number
  total_missed_distance_km: number
  is_you: boolean
}

export type Leaderboard = {
  date: string
  player_count: number
  entries: LeaderboardEntry[]
  context_entries: LeaderboardEntry[]
  your_entry: LeaderboardEntry
}

type GuessHistoryEntry = {
  districtId: number
  districtName: string
  correct: boolean
  distanceKm: number | null
  solvedPinIndex: number | null
}

type ApiGuessHistoryEntry = {
  district_id: number
  district_name: string
  correct: boolean
  distance_km: number | null
  solved_pin_index: number | null
}

export type Progress = {
  date: string
  budgetRemaining: number
  solvedPinIndices: number[]
  reveals: Reveal[]
  missedDistricts: MissedDistrict[]
  guessHistory: GuessHistoryEntry[]
  status: 'in_progress' | 'finished'
  finishReason: 'solved' | 'budget' | 'gave_up' | null
}

export type Feedback = {
  kind: 'correct' | 'miss' | 'error'
  message: string
}

export const requestedSeed = typeof window === 'undefined'
  ? null
  : new URLSearchParams(window.location.search).get('seed')

function storageKey(challenge: Challenge) {
  return challenge.mode === 'daily'
    ? `hamburg-whereabouts:${challenge.generation_version}:${challenge.id}`
    : `hamburg-whereabouts:${challenge.generation_version}:seed:${challenge.id}`
}

export function loadProgress(
  challenge: Challenge,
  storage: Pick<Storage, 'getItem'> = localStorage,
): Progress {
  const initial: Progress = {
    date: challenge.id,
    budgetRemaining: challenge.initial_budget,
    solvedPinIndices: [],
    reveals: [],
    missedDistricts: [],
    guessHistory: [],
    status: 'in_progress',
    finishReason: null,
  }
  try {
    const stored = storage.getItem(storageKey(challenge))
    if (!stored) return initial
    const parsed = JSON.parse(stored) as Partial<Progress>
    if (
      parsed.date !== challenge.id ||
      typeof parsed.budgetRemaining !== 'number' ||
      parsed.budgetRemaining < 0 ||
      parsed.budgetRemaining > challenge.initial_budget ||
      !Array.isArray(parsed.solvedPinIndices) ||
      !Array.isArray(parsed.reveals)
    ) {
      return initial
    }
    return {
      date: challenge.id,
      budgetRemaining: parsed.budgetRemaining,
      solvedPinIndices: parsed.solvedPinIndices,
      reveals: parsed.reveals,
      missedDistricts: Array.isArray(parsed.missedDistricts) ? parsed.missedDistricts : [],
      guessHistory: Array.isArray(parsed.guessHistory) ? parsed.guessHistory : [],
      status: parsed.status === 'finished' ? 'finished' : 'in_progress',
      finishReason: parsed.finishReason === 'solved' || parsed.finishReason === 'budget' || parsed.finishReason === 'gave_up'
        ? parsed.finishReason
        : null,
    }
  } catch {
    return initial
  }
}

export function progressFromChallenge(challenge: Challenge): Progress {
  if (challenge.mode === 'seeded' || challenge.state_source === 'anonymous') {
    return loadProgress(challenge)
  }
  const solvedPinIndices = challenge.guess_history.flatMap((entry) => (
    entry.correct && entry.solved_pin_index !== null ? [entry.solved_pin_index] : []
  ))
  return {
    date: challenge.id,
    budgetRemaining: challenge.budget_remaining,
    solvedPinIndices,
    reveals: challenge.solved_pins,
    missedDistricts: challenge.missed_districts,
    guessHistory: challenge.guess_history.map((entry) => ({
      districtId: entry.district_id,
      districtName: entry.district_name,
      correct: entry.correct,
      distanceKm: entry.distance_km,
      solvedPinIndex: entry.solved_pin_index,
    })),
    status: challenge.status,
    finishReason: challenge.status === 'finished'
      ? challenge.finish_reason
        ?? (solvedPinIndices.length === challenge.pins.length ? 'solved' : challenge.budget_remaining === 0 ? 'budget' : 'gave_up')
      : null,
  }
}

function mergeMissedDistricts(existing: MissedDistrict[], incoming: MissedDistrict) {
  const byId = new Map(existing.map((district) => [district.district_id, district]))
  byId.set(incoming.district_id, incoming)
  return [...byId.values()]
}

function mergeReveals(existing: Reveal[], incoming: Reveal[]) {
  const byIndex = new Map(existing.map((reveal) => [reveal.index, reveal]))
  incoming.forEach((reveal) => byIndex.set(reveal.index, reveal))
  return [...byIndex.values()].sort((a, b) => a.index - b.index)
}

export function advanceProgress(
  challenge: Challenge,
  progress: Progress,
  district: District,
  result: GuessResult,
): Progress {
  const solvedPinIndices = result.solved_pin_index === null
    ? progress.solvedPinIndices
    : [...new Set([...progress.solvedPinIndices, result.solved_pin_index])]
  return {
    ...progress,
    budgetRemaining: result.budget_remaining,
    solvedPinIndices,
    reveals: mergeReveals(progress.reveals, result.reveals),
    missedDistricts: result.missed_district
      ? mergeMissedDistricts(progress.missedDistricts, result.missed_district)
      : progress.missedDistricts,
    guessHistory: [
      ...progress.guessHistory,
      {
        districtId: district.id,
        districtName: district.name,
        correct: result.correct,
        distanceKm: result.distance_km,
        solvedPinIndex: result.solved_pin_index,
      },
    ],
    status: result.status,
    finishReason: result.status === 'finished'
      ? solvedPinIndices.length === challenge.pins.length ? 'solved' : 'budget'
      : null,
  }
}

export function useDailyChallenge(account: AccountIdentity | null) {
  const { t } = useTranslation()
  const [screen, setScreen] = useState<'start' | 'game' | 'finished'>('start')
  const [challenge, setChallenge] = useState<Challenge | null>(null)
  const [districts, setDistricts] = useState<District[]>([])
  const [progress, setProgress] = useState<Progress | null>(null)
  const [feedback, setFeedback] = useState<Feedback | null>(null)
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [leaderboard, setLeaderboard] = useState<Leaderboard | null>(null)
  const [leaderboardError, setLeaderboardError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    const challengePath = requestedSeed
      ? `/api/challenges/${encodeURIComponent(requestedSeed)}`
      : '/api/daily'
    Promise.all([
      apiFetch<ChallengeResponse>(challengePath),
      apiFetch<District[]>('/api/districts'),
    ])
      .then(([response, districtList]) => {
        if (cancelled) return
        const loadedChallenge: Challenge = requestedSeed
          ? {
              ...response,
              mode: 'seeded',
              id: requestedSeed,
              missed_districts: [],
              guess_history: [],
              state_source: 'anonymous',
            }
          : { ...response, mode: 'daily', id: response.date ?? '' }
        setChallenge(loadedChallenge)
        setDistricts(districtList)
        setProgress(progressFromChallenge(loadedChallenge))
      })
      .catch((reason: unknown) => {
        if (!cancelled) {
          setError(apiErrorMessage(reason, i18n.t.bind(i18n), 'daily.loadError'))
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    if (account && challenge?.mode === 'daily' && progress?.status === 'finished' && challenge.state_source === 'account') {
      void loadLeaderboard(challenge.id)
    }
  }, [account, challenge?.id, challenge?.mode, challenge?.state_source, progress?.status])

  async function loadLeaderboard(date: string) {
    try {
      setLeaderboard(await apiFetch<Leaderboard>(`/api/leaderboard/${date}`))
      setLeaderboardError(null)
    } catch (reason) {
      setLeaderboardError(reason instanceof Error ? reason.message : 'Could not load standings.')
    }
  }

  async function handleAuthenticated(authenticatedAccount: AccountIdentity) {
    if (challenge?.mode === 'seeded') return
    if (challenge && progress?.status === 'finished' && challenge.state_source === 'anonymous') {
      const response = await apiFetch<ChallengeResponse>('/api/daily/adopt', {
        method: 'POST',
        body: JSON.stringify({
          challenge_date: challenge.id,
          budget_remaining: progress.budgetRemaining,
          solved_pin_indices: progress.solvedPinIndices,
          guesses: progress.guessHistory.map((entry) => ({ district_id: entry.districtId })),
        }),
      })
      const daily: Challenge = { ...response, mode: 'daily', id: response.date ?? '' }
      setChallenge(daily)
      setProgress(progressFromChallenge(daily))
      await loadLeaderboard(daily.id)
      return
    }
    const response = await apiFetch<ChallengeResponse>('/api/daily')
    const daily: Challenge = { ...response, mode: 'daily', id: response.date ?? '' }
    setChallenge(daily)
    setProgress(progressFromChallenge(daily))
    if (daily.status === 'finished' && authenticatedAccount) await loadLeaderboard(daily.id)
  }

  function begin() {
    if (!progress) return
    track(challenge?.mode === 'seeded' ? 'seeded_started' : 'daily_started', challenge?.mode === 'seeded' ? { seed: challenge.id } : {})
    setScreen(progress.status === 'finished' ? 'finished' : 'game')
  }

  function returnToStart() {
    setFeedback(null)
    setScreen('start')
  }

  async function checkGuess(district: District) {
    if (!challenge || !progress || submitting || progress.status === 'finished') return false
    if (progress.guessHistory.some((entry) => entry.districtId === district.id)) {
      setFeedback({ kind: 'error', message: t('daily.alreadyGuessed', { district: district.name }) })
      return false
    }

    setSubmitting(true)
    setFeedback(null)
    try {
      const guessPath = challenge.mode === 'daily'
        ? '/api/daily/guess'
        : `/api/challenges/${encodeURIComponent(challenge.id)}/guess`
      const body = challenge.mode === 'daily'
        ? {
            challenge_date: challenge.id,
            guessed_district_id: district.id,
            anonymous_state: {
              budget_remaining: progress.budgetRemaining,
              solved_pin_indices: progress.solvedPinIndices,
            },
          }
        : {
            guessed_district_id: district.id,
            anonymous_state: {
              budget_remaining: progress.budgetRemaining,
              solved_pin_indices: progress.solvedPinIndices,
            },
          }
      const result = await apiFetch<GuessResult>(guessPath, {
        method: 'POST',
        body: JSON.stringify(body),
      })
      const next = advanceProgress(challenge, progress, district, result)
      if (challenge.state_source === 'anonymous') {
        localStorage.setItem(storageKey(challenge), JSON.stringify(next))
      }
      setProgress(next)
      setFeedback(
        result.correct
          ? { kind: 'correct', message: t('daily.found', { district: district.name }) }
          : { kind: 'miss', message: t('daily.distance', { district: district.name, distance: new Intl.NumberFormat(activeLanguage(), { style: 'unit', unit: 'kilometer', maximumFractionDigits: 1 }).format(result.distance_km ?? 0) }) },
      )
      if (result.status === 'finished') {
        track(challenge.mode === 'seeded' ? 'seeded_completed' : 'daily_completed', {
          reason: next.finishReason ?? 'finished',
          pins_solved: next.solvedPinIndices.length,
          guesses_spent: challenge.initial_budget - result.budget_remaining,
          ...(challenge.mode === 'seeded' ? { seed: challenge.id } : {}),
        })
        setScreen('finished')
        if (account && challenge.mode === 'daily') await loadLeaderboard(challenge.id)
      }
      return true
    } catch (reason) {
      setFeedback({
        kind: 'error',
        message: apiErrorMessage(reason, t, 'daily.guessError'),
      })
      return false
    } finally {
      setSubmitting(false)
    }
  }

  async function giveUp() {
    if (!challenge || !progress || submitting || progress.status === 'finished') return false
    setSubmitting(true)
    setFeedback(null)
    try {
      const giveUpPath = challenge.mode === 'daily'
        ? '/api/daily/give-up'
        : `/api/challenges/${encodeURIComponent(challenge.id)}/give-up`
      const body = challenge.mode === 'daily'
        ? {
            challenge_date: challenge.id,
            anonymous_state: {
              budget_remaining: progress.budgetRemaining,
              solved_pin_indices: progress.solvedPinIndices,
            },
          }
        : {
            anonymous_state: {
              budget_remaining: progress.budgetRemaining,
              solved_pin_indices: progress.solvedPinIndices,
            },
          }
      const result = await apiFetch<GiveUpResult>(giveUpPath, {
        method: 'POST',
        body: JSON.stringify(body),
      })
      const next: Progress = {
        ...progress,
        budgetRemaining: result.budget_remaining,
        reveals: mergeReveals(progress.reveals, result.reveals),
        status: result.status,
        finishReason: 'gave_up',
      }
      if (challenge.state_source === 'anonymous') {
        localStorage.setItem(storageKey(challenge), JSON.stringify(next))
      }
      setProgress(next)
      track(challenge.mode === 'seeded' ? 'seeded_completed' : 'daily_completed', {
        reason: 'gave_up',
        pins_solved: progress.solvedPinIndices.length,
        guesses_spent: challenge.initial_budget - result.budget_remaining,
        ...(challenge.mode === 'seeded' ? { seed: challenge.id } : {}),
      })
      setScreen('finished')
      if (account && challenge.mode === 'daily') await loadLeaderboard(challenge.id)
      return true
    } catch (reason) {
      setFeedback({
        kind: 'error',
        message: apiErrorMessage(reason, t, 'daily.giveUpError'),
      })
      return false
    } finally {
      setSubmitting(false)
    }
  }

  return {
    screen,
    challenge,
    districts,
    progress,
    feedback,
    loading,
    submitting,
    error,
    leaderboard,
    leaderboardError,
    setFeedback,
    begin,
    returnToStart,
    checkGuess,
    giveUp,
    handleAuthenticated,
    loadLeaderboard,
  }
}
