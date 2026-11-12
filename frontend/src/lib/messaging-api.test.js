import AxiosMockAdapter from 'axios-mock-adapter'
import Cookies from 'js-cookie'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import api, { messagingAPI, productsAPI } from './api'

let apiMock

beforeEach(() => {
  Cookies.set('csrftoken', 'csrf-test')
  apiMock = new AxiosMockAdapter(api)
})

afterEach(() => {
  apiMock.restore()
})

describe('Phase 16 API clients', () => {
  it('reveals a phone through the audited product endpoint', async () => {
    apiMock.onPost('/products/12/reveal-phone/').reply(200, {
      phone_number: '+213555123400',
    })

    const response = await productsAPI.revealPhone(12)

    expect(response.data.phone_number).toBe('+213555123400')
    expect(apiMock.history.post[0].url).toBe('/products/12/reveal-phone/')
    expect(JSON.parse(apiMock.history.post[0].data)).toEqual({})
  })

  it('starts a conversation with the listing id', async () => {
    apiMock.onPost('/messages/conversations/').reply(201, { id: 4 })

    const response = await messagingAPI.startConversation(12)

    expect(response.data.id).toBe(4)
    expect(JSON.parse(apiMock.history.post[0].data)).toEqual({
      listing_id: 12,
    })
  })

  it('polls messages with an after cursor', async () => {
    apiMock.onGet('/messages/conversations/4/messages/').reply(200, {
      results: [],
      next_after: null,
    })

    await messagingAPI.messages(4, { after: 9 })

    expect(apiMock.history.get[0].params).toEqual({ after: 9 })
  })

  it('wires archive, offers, block and report endpoints', async () => {
    apiMock.onPatch('/messages/conversations/4/').reply(200, {})
    apiMock.onPost('/messages/conversations/4/offers/').reply(201, {})
    apiMock.onPost('/messages/offers/8/accept/').reply(200, {})
    apiMock.onPost('/messages/users/3/block/').reply(200, {})
    apiMock.onDelete('/messages/users/3/block/').reply(200, {})
    apiMock.onPost('/messages/reports/').reply(201, {})

    await messagingAPI.archive(4, true)
    await messagingAPI.createOffer(4, { amount: '90.00', note: 'Hi' })
    await messagingAPI.offerAction(8, 'accept')
    await messagingAPI.blockUser(3)
    await messagingAPI.unblockUser(3)
    await messagingAPI.report({ message_id: 2, reason: 'SCAM' })

    expect(JSON.parse(apiMock.history.patch[0].data)).toEqual({
      is_archived: true,
    })
    expect(JSON.parse(apiMock.history.post[0].data)).toEqual({
      amount: '90.00',
      note: 'Hi',
    })
    expect(apiMock.history.post[1].url).toBe('/messages/offers/8/accept/')
    expect(apiMock.history.delete[0].url).toBe('/messages/users/3/block/')
    expect(JSON.parse(apiMock.history.post[3].data)).toEqual({
      message_id: 2,
      reason: 'SCAM',
    })
  })
})
