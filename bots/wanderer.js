/**
 * Simple load-generation bot. Connects, wanders, occasionally digs.
 * Usage: node wanderer.js [bot-count] [host] [port]
 */
const mineflayer = require('mineflayer')

const BOT_COUNT = parseInt(process.argv[2] || '3', 10)
const HOST = process.argv[3] || '127.0.0.1'
const PORT = parseInt(process.argv[4] || '25565', 10)

function launchBot(name) {
  const bot = mineflayer.createBot({
    host: HOST,
    port: PORT,
    username: name,
    version: '1.20.4',
    hideErrors: false,
  })

  let wanderInterval = null

  bot.on('spawn', () => {
    console.log(`[${name}] spawned at ${bot.entity.position}`)
    wanderInterval = setInterval(() => wander(bot, name), 3000 + Math.random() * 4000)
  })

  bot.on('error', (err) => {
    console.error(`[${name}] error: ${err.message}`)
  })

  bot.on('kicked', (reason) => {
    console.log(`[${name}] kicked: ${reason}`)
    if (wanderInterval) clearInterval(wanderInterval)
  })

  bot.on('end', () => {
    console.log(`[${name}] disconnected`)
    if (wanderInterval) clearInterval(wanderInterval)
  })

  return bot
}

function wander(bot, name) {
  const dx = (Math.random() - 0.5) * 10
  const dz = (Math.random() - 0.5) * 10
  const pos = bot.entity.position
  const target = pos.offset(dx, 0, dz)

  bot.lookAt(target)

  bot.setControlState('forward', true)
  setTimeout(() => {
    bot.setControlState('forward', false)
    if (Math.random() < 0.1) {
      bot.setControlState('jump', true)
      setTimeout(() => bot.setControlState('jump', false), 300)
    }
  }, 1000 + Math.random() * 2000)
}

const bots = []
for (let i = 0; i < BOT_COUNT; i++) {
  setTimeout(() => {
    bots.push(launchBot(`SREBot${i + 1}`))
  }, i * 2000)
}

process.on('SIGINT', () => {
  console.log('shutting down bots...')
  bots.forEach(b => b.quit())
  process.exit(0)
})

process.on('SIGTERM', () => {
  bots.forEach(b => b.quit())
  process.exit(0)
})
