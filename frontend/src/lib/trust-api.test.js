import AxiosMockAdapter from 'axios-mock-adapter'
import Cookies from 'js-cookie'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import api, { trustAPI } from './api'

let apiMock

beforeEach(() => {
  Cookies.set('csrftoken', 'csrf-test')
  apiMock = new AxiosMockAdapter(api)
})

afterEach(() => {
  apiMock.restore()
})

describe('Phase 17 trust API clients', () => {
  it('reads the public safety centre', async () => {
    apiMock.onGet('/trust/safety-center/').reply(200, {
      language: 'en',
      title: 'Safety centre',
      sections: [],
    })

    const response = await trustAPI.safetyCenter()

    expect(response.data.title).toBe('Safety centre')
  })

  it('submits identity and store verification separately', async () => {
    apiMock.onPost('/trust/verification/').reply(201, { id: 1 })
    apiMock.onPost('/trust/store-verification/').reply(201, { id: 2 })

    await trustAPI.submitIdentity({
      document_image_id: 9,
      document_type: 'PASSPORT',
    })
    await trustAPI.submitStore({
      commercial_register_number: 'RC-1',
      nif_number: '',
    })

    expect(JSON.parse(apiMock.history.post[0].data)).toEqual({
      document_image_id: 9,
      document_type: 'PASSPORT',
    })
    expect(apiMock.history.post[1].url).toBe('/trust/store-verification/')
    expect(JSON.parse(apiMock.history.post[1].data)).toEqual({
      commercial_register_number: 'RC-1',
      nif_number: '',
    })
  })

  it('files an appeal with the right target key', async () => {
    apiMock.onPost('/trust/appeals/').reply(201, { id: 7, status: 'OPEN' })

    const response = await trustAPI.createAppeal({
      kind: 'LISTING',
      listing_id: 3,
      message: 'This is a bicycle.',
    })

    expect(response.data.id).toBe(7)
    expect(JSON.parse(apiMock.history.post[0].data)).toEqual({
      kind: 'LISTING',
      listing_id: 3,
      message: 'This is a bicycle.',
    })
  })

  it('passes queue filters and posts staff actions', async () => {
    apiMock.onGet('/trust/admin/reports/').reply(200, [])
    apiMock
      .onPost('/trust/admin/reports/5/action/')
      .reply(200, { id: 5, status: 'ACTIONED' })
    apiMock.onGet('/trust/admin/overview/').reply(200, { open_reports: 1 })

    await trustAPI.admin.reports({ status: 'OPEN', overdue: 1 })
    await trustAPI.admin.reportAction(5, {
      action: 'action',
      action_taken: 'listing_removed',
      resolution: 'Counterfeit',
    })
    const overview = await trustAPI.admin.overview()

    expect(apiMock.history.get[0].params).toEqual({
      status: 'OPEN',
      overdue: 1,
    })
    expect(JSON.parse(apiMock.history.post[0].data)).toEqual({
      action: 'action',
      action_taken: 'listing_removed',
      resolution: 'Counterfeit',
    })
    expect(overview.data.open_reports).toBe(1)
  })

  it('wires verification, appeal, blocklist and mass actions', async () => {
    apiMock.onPost('/trust/admin/verifications/2/action/').reply(200, {})
    apiMock.onPost('/trust/admin/appeals/3/action/').reply(200, {})
    apiMock.onGet('/trust/admin/blocklist/').reply(200, [])
    apiMock.onPost('/trust/admin/blocklist/').reply(201, { id: 1 })
    apiMock.onDelete('/trust/admin/blocklist/1/').reply(204)
    apiMock.onPost('/trust/admin/mass-action/').reply(200, { affected: 2 })

    await trustAPI.admin.verificationAction(2, { action: 'approve' })
    await trustAPI.admin.appealAction(3, { action: 'approve' })
    await trustAPI.admin.blocklist({ active: 1 })
    await trustAPI.admin.addBlocklist({
      kind: 'PHONE',
      value: '0555123456',
      reason: 'Scam',
    })
    await trustAPI.admin.removeBlocklist(1)
    const mass = await trustAPI.admin.massAction({
      identifier: '0555123456',
      action: 'ban',
    })

    expect(apiMock.history.post[0].url).toBe(
      '/trust/admin/verifications/2/action/'
    )
    expect(apiMock.history.get[0].params).toEqual({ active: 1 })
    expect(apiMock.history.delete[0].url).toBe('/trust/admin/blocklist/1/')
    expect(mass.data.affected).toBe(2)
  })
})
