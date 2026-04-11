const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

async function request(method, path, body) {
  const opts = { method, headers: { 'Content-Type': 'application/json' } }
  if (body) opts.body = JSON.stringify(body)
  const res = await fetch(`${API}${path}`, opts)
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text)
  }
  return res.json()
}

// ── Sessions ──────────────────────────────────────────────────────────────────
export const startSession = (body) =>
  request('POST', '/sessions/start', body)

export const getSession = (sessionId) =>
  request('GET', `/sessions/${sessionId}`)

export const deleteSession = (sessionId) =>
  request('DELETE', `/sessions/${sessionId}`)

// ── Prerequisite ──────────────────────────────────────────────────────────────
export const submitPrereqQuiz = (sessionId, answers) =>
  request('POST', `/prereq/${sessionId}/submit`, { answers })

export const getPrereqStatus = (sessionId) =>
  request('GET', `/prereq/${sessionId}/status`)

// ── Planning ──────────────────────────────────────────────────────────────────
export const submitApproach = (sessionId, approach) =>
  request('POST', `/planning/${sessionId}/approach`, { approach })

export const getRoadmap = (sessionId) =>
  request('GET', `/planning/${sessionId}/roadmap`)

export const getAnalysis = (sessionId) =>
  request('GET', `/planning/${sessionId}/analysis`)

// ── Weekly ────────────────────────────────────────────────────────────────────
export const startWeek = (sessionId) =>
  request('POST', `/weekly/${sessionId}/start`)

export const checkCompletion = (sessionId) =>
  request('POST', `/weekly/${sessionId}/check`)

export const getTaskQuiz = (sessionId) =>
  request('GET', `/weekly/${sessionId}/quiz`)

export const submitTaskQuiz = (sessionId, answers) =>
  request('POST', `/weekly/${sessionId}/quiz/submit`, { answers })

export const getWeeklyTasks = (sessionId) =>
  request('GET', `/weekly/${sessionId}/tasks`)

export const getWeeklyScore = (sessionId) =>
  request('GET', `/weekly/${sessionId}/score`)

// ── Teacher ───────────────────────────────────────────────────────────────────
export const getProjects = () =>
  request('GET', '/projects')

export const createProject = (body) =>
  request('POST', '/projects', body)

export const getDashboard = () =>
  request('GET', '/dashboard')
