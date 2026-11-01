const mineflayer = require('mineflayer')
const { Vec3 } = require('vec3')

const VERSION = '1.20.4'
const RECONNECT_MS = 5000
const BANNED_RETRY_MS = 15000
const PROBE_TIMEOUT_MS = 20000

const spec = JSON.parse(process.argv[2] || '{}')
const port = spec.port || 25565
const agents = []
let stopping = false

function emit(bot, event, detail) {
  process.stdout.write(JSON.stringify({ t: Date.now(), bot, event, detail: detail === undefined ? null : detail }) + '\n')
}

function chatText(reason) {
  if (reason == null) return ''
  if (typeof reason === 'string') {
    try { return chatText(JSON.parse(reason)) } catch { return reason }
  }
  if (typeof reason !== 'object') return String(reason)
  if (Array.isArray(reason)) return reason.map(chatText).join('')
  if (reason.type && 'value' in reason) return chatText(reason.value)
  let out = ''
  if (reason.text != null) out += chatText(reason.text)
  if (reason.translate != null) {
    out += chatText(reason.translate)
    if (reason.with) out += ' ' + chatText(reason.with)
  }
  if (reason.extra) out += chatText(reason.extra)
  if (!out && reason[''] != null) out = chatText(reason[''])
  return out || JSON.stringify(reason)
}

function exitAfterFlush() {
  process.stdout.write('', () => process.exit(0))
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const coords = (p) => [p.x, p.y, p.z]

async function waitCreative(agent, bot) {
  while (agent.live(bot) && bot.game.gameMode !== 'creative') await sleep(250)
  return agent.live(bot)
}

function standPoint(bot, target) {
  const offsets = [[2, 1, 0], [-2, 1, 0], [0, 1, 2], [0, 1, -2], [2, 2, 2], [-2, 2, -2], [2, 2, -2], [-2, 2, 2]]
  const center = target.offset(0.5, 0, 0.5)
  let best = null
  for (const [dx, dy, dz] of offsets) {
    const p = center.offset(dx, dy, dz)
    const feet = bot.blockAt(p.floored())
    const head = bot.blockAt(p.floored().offset(0, 1, 0))
    if (!feet || !head || feet.boundingBox !== 'empty' || head.boundingBox !== 'empty') continue
    if (!best || p.distanceTo(bot.entity.position) < best.distanceTo(bot.entity.position)) best = p
  }
  return best || center.offset(0, 3, 0)
}

async function flyNear(bot, target) {
  if (bot.entity.position.offset(0, 1.62, 0).distanceTo(target.offset(0.5, 0.5, 0.5)) <= 5.8) return
  await Promise.race([bot.creative.flyTo(standPoint(bot, target)), sleep(6000)])
}

const chunksLoaded = (bot) => Promise.race([bot.waitForChunksToLoad(), sleep(5000)])

const roles = {
  async resident(agent, bot) {
    while (agent.live(bot)) {
      await sleep(3000 + Math.random() * 3000)
      if (!agent.live(bot)) return
      await bot.look(Math.random() * Math.PI * 2, (Math.random() - 0.5) * 0.6, false)
      if (Math.random() < 0.3) {
        bot.setControlState('jump', true)
        await sleep(300)
        if (agent.live(bot)) bot.setControlState('jump', false)
      }
    }
  },

  async griefer(agent, bot) {
    const interval = agent.cfg.interval_ms || 1500
    const targets = (agent.cfg.targets || []).map(([x, y, z]) => new Vec3(x, y, z))
    if (!(await waitCreative(agent, bot))) return
    await chunksLoaded(bot)
    while (agent.live(bot)) {
      const block = targets.map((p) => bot.blockAt(p)).find((b) => b && b.name !== 'air' && b.name !== 'cave_air' && b.name !== 'void_air')
      if (!block) { await sleep(interval); continue }
      try {
        await flyNear(bot, block.position)
        await bot.dig(block, true)
        emit(agent.name, 'dug', { pos: coords(block.position), block: block.name })
      } catch (err) {
        if (agent.live(bot)) emit(agent.name, 'error', `dig ${coords(block.position)}: ${err.message}`)
      }
      await sleep(interval)
    }
  },

  async builder(agent, bot) {
    const interval = agent.cfg.interval_ms || 2000
    const blockName = agent.cfg.block || 'oak_planks'
    const spots = (agent.cfg.blocks || []).map(([x, y, z]) => new Vec3(x, y, z))
    const Item = require('prismarine-item')(bot.registry)
    const itemId = bot.registry.itemsByName[blockName].id
    if (!(await waitCreative(agent, bot))) return
    await chunksLoaded(bot)
    while (agent.live(bot)) {
      const spot = spots.find((p) => { const b = bot.blockAt(p); return b && b.boundingBox === 'empty' })
      if (!spot) { await sleep(interval); continue }
      try {
        const held = bot.inventory.slots[36]
        if (!held || held.type !== itemId) await bot.creative.setInventorySlot(36, new Item(itemId, 64))
        if (bot.quickBarSlot !== 0) bot.setQuickBarSlot(0)
        await flyNear(bot, spot)
        await bot.placeBlock(bot.blockAt(spot.offset(0, -1, 0)), new Vec3(0, 1, 0))
        emit(agent.name, 'placed', { pos: coords(spot), block: blockName })
      } catch (err) {
        const placed = bot.blockAt(spot)
        if (placed && placed.name === blockName) emit(agent.name, 'placed', { pos: coords(spot), block: blockName })
        else if (agent.live(bot)) emit(agent.name, 'error', `place ${coords(spot)}: ${err.message}`)
      }
      await sleep(interval)
    }
  },
}

function startAgent(cfg) {
  const agent = { name: cfg.name, role: cfg.role, cfg, bot: null, done: false, timer: null }
  agent.live = (bot) => !stopping && agent.bot === bot && !bot._closed
  agents.push(agent)

  function finish() {
    agent.done = true
    agent.bot = null
    if (agents.every((a) => a.role === 'prober' && a.done)) exitAfterFlush()
  }

  function connect() {
    agent.timer = null
    if (stopping) return
    let bot
    try {
      bot = mineflayer.createBot({ host: '127.0.0.1', port, username: cfg.name, version: VERSION, auth: 'offline', hideErrors: true })
    } catch (err) {
      emit(cfg.name, 'error', err.message)
      return closed(null, err.message)
    }
    agent.bot = bot
    let spawned = false
    let probeTimer = null
    if (cfg.role === 'prober') {
      probeTimer = setTimeout(() => { if (!spawned) closed(bot, 'timeout') }, PROBE_TIMEOUT_MS)
    }

    bot.once('spawn', () => {
      spawned = true
      emit(cfg.name, 'spawn', { pos: coords(bot.entity.position.floored()) })
      if (cfg.role === 'prober') {
        clearTimeout(probeTimer)
        emit(cfg.name, 'join_ok', null)
        bot._closed = true
        bot.quit()
        return finish()
      }
      const run = roles[cfg.role]
      if (run) run(agent, bot).catch((err) => { if (agent.live(bot)) emit(cfg.name, 'error', `${cfg.role}: ${err.message}`) })
    })
    bot.on('kicked', (reason) => {
      const text = chatText(reason)
      emit(cfg.name, 'kicked', text)
      closed(bot, text)
    })
    bot.on('error', (err) => {
      emit(cfg.name, 'error', err.message)
      closed(bot, err.message)
    })
    bot.on('end', (reason) => {
      emit(cfg.name, 'end', String(reason))
      closed(bot, String(reason))
    })

    function closed(b, reason) {
      if (b && b._closed) return
      if (b) {
        b._closed = true
        clearTimeout(probeTimer)
        try { b.end() } catch {}
      }
      if (stopping) return
      if (cfg.role === 'prober') {
        emit(cfg.name, 'join_fail', reason)
        return finish()
      }
      const banned = /banned/i.test(reason)
      if (banned) emit(cfg.name, 'banned', reason)
      agent.timer = setTimeout(connect, banned ? BANNED_RETRY_MS : RECONNECT_MS)
    }
  }

  connect()
}

function shutdown() {
  if (stopping) return
  stopping = true
  for (const a of agents) {
    clearTimeout(a.timer)
    if (a.bot) { try { a.bot.quit() } catch {} }
  }
  setTimeout(exitAfterFlush, 500)
}

process.on('SIGTERM', shutdown)
process.on('SIGINT', shutdown)
process.on('uncaughtException', (err) => emit(null, 'error', `uncaught: ${err.message}`))
process.on('unhandledRejection', (err) => emit(null, 'error', `unhandled: ${err && err.message}`))

for (const cfg of spec.bots || []) startAgent(cfg)
if (!agents.length) exitAfterFlush()
