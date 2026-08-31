import { describe, expect, it } from 'vitest'
import {
  advanceProgress,
  loadProgress,
  progressFromChallenge,
} from './useDailyChallenge'
import type { Challenge, Progress } from './useDailyChallenge'

const challenge: Challenge = {
  generation_version: 'daily-districts-v2',
  date: '2026-08-31',
  pins: [
    { index: 0, lat: 53.5, lng: 10 },
    { index: 1, lat: 53.6, lng: 10.1 },
  ],
  initial_budget: 10,
  budget_remaining: 10,
  solved_pins: [],
  missed_districts: [],
  guess_history: [],
  status: 'in_progress',
  state_source: 'anonymous',
  finish_reason: null,
  mode: 'daily',
  id: '2026-08-31',
}

const initialProgress: Progress = {
  date: challenge.id,
  budgetRemaining: 10,
  solvedPinIndices: [],
  reveals: [],
  missedDistricts: [],
  guessHistory: [],
  status: 'in_progress',
  finishReason: null,
}

describe('Daily Challenge workflow transitions', () => {
  it('restores missed District geometry for an active browser game', () => {
    const stored = JSON.stringify({
      ...initialProgress,
      missedDistricts: [{
        district_id: 17,
        district_name: 'Eimsbüttel',
        boundary: { type: 'MultiPolygon', coordinates: [] },
        distance_km: 1.2,
      }],
    })

    const progress = loadProgress(challenge, { getItem: () => stored })

    expect(progress.missedDistricts).toEqual([{
      district_id: 17,
      district_name: 'Eimsbüttel',
      boundary: { type: 'MultiPolygon', coordinates: [] },
      distance_km: 1.2,
    }])
  })

  it('maps trusted Account progress into the browser Game model', () => {
    const progress = progressFromChallenge({
      ...challenge,
      state_source: 'account',
      budget_remaining: 8,
      solved_pins: [{
        index: 1,
        district_name: 'Eimsbüttel',
        boundary: { type: 'MultiPolygon' },
      }],
      guess_history: [{
        district_id: 17,
        district_name: 'Eimsbüttel',
        correct: true,
        distance_km: null,
        solved_pin_index: 1,
      }],
    })

    expect(progress.budgetRemaining).toBe(8)
    expect(progress.solvedPinIndices).toEqual([1])
    expect(progress.guessHistory[0]?.districtName).toBe('Eimsbüttel')
  })

  it('adds a wrong District boundary to active map progress', () => {
    const missedDistrict = {
      district_id: 17,
      district_name: 'Eimsbüttel',
      boundary: { type: 'MultiPolygon' as const, coordinates: [] },
      distance_km: 1.2,
    }

    const progress = advanceProgress(
      challenge,
      initialProgress,
      { id: 17, name: 'Eimsbüttel' },
      {
        correct: false,
        solved_pin_index: null,
        distance_km: 1.2,
        missed_district: missedDistrict,
        budget_remaining: 9,
        status: 'in_progress',
        reveals: [],
      },
    )

    expect(progress.status).toBe('in_progress')
    expect(progress.missedDistricts).toEqual([missedDistrict])
  })

  it('finishes a Game when the final Pin is solved', () => {
    const progress = advanceProgress(
      challenge,
      { ...initialProgress, solvedPinIndices: [0] },
      { id: 17, name: 'Eimsbüttel' },
      {
        correct: true,
        solved_pin_index: 1,
        distance_km: null,
        missed_district: null,
        budget_remaining: 8,
        status: 'finished',
        reveals: [{
          index: 1,
          district_name: 'Eimsbüttel',
          boundary: { type: 'MultiPolygon' },
        }],
      },
    )

    expect(progress.status).toBe('finished')
    expect(progress.finishReason).toBe('solved')
    expect(progress.solvedPinIndices).toEqual([0, 1])
    expect(progress.guessHistory).toHaveLength(1)
  })
})
