// Global setup: seed the verified e2e fixtures (buyer, seller+store, listing).
// Registration only creates *unverified* users and login rejects those (403),
// so the smoke journeys log in with the accounts created by
// `python manage.py seed_e2e`. Talks straight to the database, so it does not
// depend on the web servers being up yet.
const { execFileSync } = require('child_process')
const path = require('path')

module.exports = async () => {
  const backendDir = path.resolve(__dirname, '../../backend')
  const python = process.platform === 'win32' ? 'python' : 'python3'

  try {
    const output = execFileSync(python, ['manage.py', 'seed_e2e'], {
      cwd: backendDir,
      encoding: 'utf8',
      stdio: ['ignore', 'pipe', 'inherit'],
    })
    console.log(output.trim())
  } catch (error) {
    console.error('e2e global setup failed to seed fixtures:')
    console.error(error.stdout || error.message)
    throw error
  }
}
