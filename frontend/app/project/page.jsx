'use client'
import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import Sidebar from '@/components/Sidebar'
import TaskCard from '@/components/TaskCard'
import RoadmapProgress from '@/components/RoadmapProgress'
import { ScoreRing, PhaseProgress, Spinner } from '@/components/ProgressAnimation'
import * as api from '@/lib/api'

const card = (extra = {}) => ({
  background: 'var(--surface)', border: '1px solid var(--border)',
  borderRadius: 12, padding: 28, marginBottom: 16, ...extra,
})

const Btn = ({ children, onClick, disabled = false, variant = 'primary', small = false }) => {
  const bg  = variant === 'primary' ? 'var(--accent)' : variant === 'green' ? 'var(--accent3)' : 'transparent'
  const col = variant === 'outline' ? 'var(--text)' : variant === 'green' ? '#0a0a0f' : '#fff'
  return (
    <button onClick={onClick} disabled={disabled} style={{
      display: 'inline-flex', alignItems: 'center', gap: 8,
      padding: small ? '8px 16px' : '12px 24px',
      borderRadius: 8, border: variant === 'outline' ? '1px solid var(--border)' : 'none',
      background: bg, color: col,
      fontFamily: 'var(--font-mono)', fontSize: small ? 12 : 14, fontWeight: 500,
      cursor: disabled ? 'not-allowed' : 'pointer', opacity: disabled ? 0.5 : 1,
    }}>
      {children}
    </button>
  )
}

const Eyebrow = ({ children }) => (
  <div style={{ fontSize: 11, letterSpacing: '0.15em', textTransform: 'uppercase', color: 'var(--accent)', marginBottom: 16 }}>
    {children}
  </div>
)

const H1 = ({ children }) => (
  <h1 style={{ fontFamily: 'var(--font-head)', fontSize: 'clamp(28px,4vw,44px)', fontWeight: 800, lineHeight: 1.05, letterSpacing: '-1px', marginBottom: 12 }}>
    {children}
  </h1>
)

const H2 = ({ children }) => (
  <div style={{ fontFamily: 'var(--font-head)', fontSize: 22, fontWeight: 700, letterSpacing: '-0.5px', marginBottom: 8 }}>
    {children}
  </div>
)

// ── QuestionCard ──────────────────────────────────────────────────────────────

function QuestionCard({ q, index, answers, setAnswers, graded }) {
  const ans     = answers[index] || ''
  const correct = q.correct_answer

  if (q.type === 'mcq') return (
    <div style={card({ marginBottom: 16 })}>
      <div style={{ fontSize: 12, color: 'var(--muted)', marginBottom: 10 }}>Q{index + 1}</div>
      <div style={{ fontSize: 15, lineHeight: 1.6, marginBottom: 16 }}>{q.question}</div>
      {(q.options || []).map(opt => {
        const letter    = opt[0]
        const isSelected = letter === ans
        const isCorrect  = graded && letter === correct
        const isWrong    = graded && isSelected && letter !== correct
        return (
          <button key={letter}
            onClick={() => !graded && setAnswers(a => ({ ...a, [index]: letter }))}
            style={{
              display: 'flex', alignItems: 'flex-start', gap: 14,
              padding: '14px 16px', width: '100%', marginBottom: 10,
              background: isCorrect ? 'rgba(61,217,164,0.1)' : isWrong ? 'rgba(240,93,93,0.1)' : isSelected ? 'rgba(123,110,246,0.1)' : 'var(--surface2)',
              border: `1px solid ${isCorrect ? 'var(--accent3)' : isWrong ? 'var(--danger)' : isSelected ? 'var(--accent)' : 'var(--border)'}`,
              borderRadius: 8, cursor: graded ? 'default' : 'pointer',
              color: isCorrect ? 'var(--accent3)' : isWrong ? 'var(--danger)' : 'var(--text)',
              fontFamily: 'var(--font-mono)', fontSize: 14, lineHeight: 1.5, textAlign: 'left',
            }}>
            <span style={{
              width: 24, height: 24, borderRadius: 6, flexShrink: 0,
              display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 12,
              background: isCorrect ? 'var(--accent3)' : isWrong ? 'var(--danger)' : isSelected ? 'var(--accent)' : 'var(--surface)',
              border: `1px solid ${isSelected || isCorrect || isWrong ? 'transparent' : 'var(--border)'}`,
              color: isSelected || isCorrect || isWrong ? (isCorrect ? '#0a0a0f' : '#fff') : 'var(--muted)',
            }}>{letter}</span>
            <span>{opt.slice(3)}</span>
          </button>
        )
      })}
    </div>
  )

  if (q.type === 'code' || q.type === 'text') return (
    <div style={card({ marginBottom: 16 })}>
      <div style={{ fontSize: 12, color: 'var(--muted)', marginBottom: 10 }}>
        Q{index + 1} — {q.type === 'text' ? 'Reflection' : 'Code'}
      </div>
      {q.type === 'code'
        ? <div style={{ background: '#0d0d14', border: '1px solid var(--border)', borderRadius: 8, padding: 16, fontFamily: 'var(--font-mono)', fontSize: 13, lineHeight: 1.7, whiteSpace: 'pre-wrap', color: '#c9d1d9', marginBottom: 12 }}>{q.question}</div>
        : <div style={{ fontSize: 15, lineHeight: 1.6, marginBottom: 12 }}>{q.question}</div>
      }
      <textarea
        readOnly={graded}
        value={ans}
        onChange={e => setAnswers(a => ({ ...a, [index]: e.target.value }))}
        placeholder={q.type === 'text' ? 'Your reflection…' : 'Your answer…'}
        rows={q.type === 'text' ? 4 : 3}
        style={{
          width: '100%', background: '#0d0d14', border: '1px solid var(--border)',
          borderRadius: 8, padding: 12, fontFamily: 'var(--font-mono)',
          fontSize: 13, color: q.type === 'text' ? 'var(--text)' : 'var(--accent3)',
          outline: 'none', resize: 'vertical',
        }}
      />
    </div>
  )
  return null
}

// ── PrereqPhase ───────────────────────────────────────────────────────────────
//
// KEY DESIGN:
//   - `localState` is the single source of truth for what's displayed.
//     It starts from the parent `state` prop but is NEVER overwritten by it
//     after the first mount — all updates come from the API response.
//   - `submit()` calls the backend, stores the result, shows graded answers.
//   - `advance()` is the ONLY place localState/index changes — called when
//     the user clicks "Next concept →" or "Retry →".
//   - The Eyebrow and concept title always read from localState.

function PrereqPhase({ sessionId, state: initialState, onDone }) {
  // localState is our private copy — we mutate it on each advance
  const [localState, setLocalState] = useState(initialState)
  const [answers,    setAnswers]    = useState({})
  const [graded,     setGraded]     = useState(false)
  const [loading,    setLoading]    = useState(false)
  const [error,      setError]      = useState('')
  const [result,     setResult]     = useState(null)  // last API response

  // Sync if parent re-mounts with a different session (edge case)
  useEffect(() => { setLocalState(initialState) }, [initialState?.current_concept_index])

  const prereqs   = localState?.prerequisites || []
  const totalConcepts = prereqs.length
  // idx is the concept currently being shown/quizzed
  const idx       = localState?.current_concept_index ?? 0
  const quiz      = localState?.quiz_results?.slice(-1)[0]

  // ── Submit: call backend, show graded answers ─────────────────────────────
  async function submit() {
    if (!quiz) return
    const ans = quiz.questions.map((_, i) => answers[i] || '')
    setLoading(true)
    setError('')
    try {
      const res = await api.submitPrereqQuiz(sessionId, ans)
      setResult(res)
      setGraded(true)   // just reveal correct/wrong — don't change anything else
    } catch (e) {
      setError(e.message)
    }
    setLoading(false)
  }

  // ── Advance: called ONLY when user explicitly clicks Next / Retry ─────────
  function advance() {
    if (!result) return

    // ── FAILED → retry same concept, same quiz, clear answers ────────────────
    if (!result.passed) {
      setAnswers({})
      setGraded(false)
      setResult(null)
      return
    }

    // ── ALL CONCEPTS DONE → tell parent to switch phase ───────────────────────
    if (result.prereqs_complete) {
      onDone('approach')
      return
    }

    // ── PASSED, MORE CONCEPTS → build the next local state from the response ──
    //
    // result.next_concept_index  = the index the backend has advanced to
    // result.next_quiz           = the quiz questions for that concept
    // result.next_concept        = name of that concept
    //
    // We do NOT trust localState.current_concept_index here — we use what
    // the backend tells us so we stay in sync even if the graph skips or
    // double-increments.

    const nextIndex = result.next_concept_index   // source of truth from backend

    const nextLocalState = {
      ...localState,
      current_concept_index: nextIndex,
      quiz_results: [
        ...localState.quiz_results,
        {
          concept:   result.next_concept,
          questions: result.next_quiz,   // already QuizQuestionOut shape
          score:     0,
          passed:    false,
        },
      ],
    }

    setLocalState(nextLocalState)
    setAnswers({})
    setGraded(false)
    setResult(null)

    // Also tell parent so its state ref stays roughly in sync
    onDone('refresh', nextLocalState)
  }

  if (!quiz) return <div><Spinner /></div>

  const passed = result?.passed
  const score  = result?.graded_score ?? quiz.score ?? 0

  return (
    <div className="fade-up">
      {/* idx is always the CURRENT concept being shown */}
      <Eyebrow>Prerequisite {idx + 1} of {totalConcepts}</Eyebrow>
      <H1>{prereqs[idx]?.concept}</H1>
      <p style={{ color: 'var(--muted)', fontSize: 14, lineHeight: 1.6, marginBottom: 8 }}>
        {prereqs[idx]?.explanation}
      </p>

      <div style={card({ borderLeft: '3px solid var(--accent2)', margin: '24px 0' })}>
        <div style={{ fontSize: 11, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--accent2)', marginBottom: 8 }}>Toy task</div>
        <div style={{ fontSize: 14, lineHeight: 1.7 }}>{prereqs[idx]?.toy_task}</div>
      </div>

      <div style={{ height: 1, background: 'var(--border)', margin: '28px 0' }} />
      <H2>Knowledge check</H2>
      <p style={{ color: 'var(--muted)', fontSize: 13, marginBottom: 24 }}>No marks — just a checkpoint.</p>

      {quiz.questions.map((q, i) => (
        <QuestionCard key={i} q={q} index={i} answers={answers} setAnswers={setAnswers} graded={graded} />
      ))}

      {error && (
        <div style={card({ borderLeft: '3px solid var(--danger)' })}>
          <span style={{ color: 'var(--danger)', fontSize: 14 }}>{error}</span>
        </div>
      )}

      {/* ── Before grading: Submit button ─────────────────────────────────── */}
      {!graded && (
        <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 24 }}>
          <Btn onClick={submit} disabled={loading}>
            {loading ? <><Spinner size={16} /> Grading…</> : 'Submit answers →'}
          </Btn>
        </div>
      )}

      {/* ── After grading: result banner + action button ───────────────────── */}
      {graded && result && (
        <>
          <div style={card({ borderLeft: `3px solid ${passed ? 'var(--accent3)' : 'var(--danger)'}` })}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <span>{passed ? '✓ Passed — ready to continue' : '✗ Not quite — review and retry'}</span>
              <span style={{ fontSize: 13, fontWeight: 600, color: passed ? 'var(--accent3)' : 'var(--danger)' }}>
                {score}/5
              </span>
            </div>
          </div>

          <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 16 }}>
            {passed ? (
              <Btn onClick={advance} disabled={loading}>
                {result.prereqs_complete
                  ? 'Write your approach →'
                  : `Next concept (${result.next_concept_index + 1}/${totalConcepts}) →`}
              </Btn>
            ) : (
              <Btn variant="outline" onClick={advance}>Retry →</Btn>
            )}
          </div>
        </>
      )}
    </div>
  )
}

// ── ApproachPhase ─────────────────────────────────────────────────────────────

function ApproachPhase({ sessionId, state, onDone }) {
  const [text,    setText]    = useState('')
  const [loading, setLoading] = useState(false)
  const [error,   setError]   = useState('')

  async function submit() {
    if (text.length < 50) { setError('Please write at least 50 characters.'); return }
    setLoading(true); setError('')
    try {
      const res = await api.submitApproach(sessionId, text)
      onDone(res)
    } catch (e) { setError(e.message) }
    setLoading(false)
  }

  return (
    <div className="fade-up">
      <Eyebrow>Planning phase</Eyebrow>
      <H1>Your <span style={{ color: 'var(--accent)' }}>approach.</span></H1>
      <p style={{ fontFamily: 'var(--font-serif)', fontStyle: 'italic', color: 'var(--muted)', fontSize: 18, marginBottom: 32 }}>
        All prerequisites cleared. Describe how you will build the project.
      </p>
      <div style={{ marginBottom: 16 }}>
        {(state?.prerequisites || []).map(p => (
          <span key={p.concept} style={{
            display: 'inline-flex', alignItems: 'center', gap: 6,
            background: 'var(--surface2)', border: '1px solid var(--accent3)',
            borderRadius: 20, padding: '5px 14px', fontSize: 13,
            color: 'var(--accent3)', marginRight: 8, marginBottom: 8,
          }}>
            ✓ {p.concept}
          </span>
        ))}
      </div>
      <div style={card()}>
        <label style={{ fontSize: 11, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--muted)', marginBottom: 12, display: 'block' }}>
          Describe your plan — mention tech, architecture, how you will connect the pieces, and the AI feature
        </label>
        <textarea value={text} onChange={e => setText(e.target.value)} rows={10}
          placeholder="I plan to build a React frontend with… The backend will use FastAPI… I'll connect them by… For the AI feature I'll call…"
          style={{ width: '100%', background: 'var(--surface2)', border: '1px solid var(--border)', borderRadius: 8, padding: '12px 14px', color: 'var(--text)', fontFamily: 'var(--font-mono)', fontSize: 14, outline: 'none', resize: 'vertical', lineHeight: 1.6 }}
        />
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 12 }}>
          <span style={{ fontSize: 12, color: 'var(--muted)' }}>{text.length} chars</span>
          <Btn onClick={submit} disabled={loading}>{loading ? <><Spinner size={16} /> Analyzing…</> : 'Analyze & build roadmap →'}</Btn>
        </div>
      </div>
      {error && <div style={card({ borderLeft: '3px solid var(--danger)' })}><span style={{ color: 'var(--danger)', fontSize: 14 }}>{error}</span></div>}
    </div>
  )
}

// ── RoadmapPhase ──────────────────────────────────────────────────────────────

function RoadmapPhase({ roadmap, analysis, currentWeek, onStart, loading }) {
  return (
    <div className="fade-up">
      <Eyebrow>Your personalised plan</Eyebrow>
      <H1>{roadmap.total_weeks}-week <span style={{ color: 'var(--accent)' }}>roadmap.</span></H1>
      {analysis && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, margin: '32px 0' }}>
          <div style={card({ borderLeft: '3px solid var(--accent3)' })}>
            <div style={{ fontSize: 11, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--accent3)', marginBottom: 12 }}>Strengths</div>
            {(analysis.positives || []).map((p, i) => (
              <div key={i} style={{ display: 'flex', gap: 10, marginBottom: 10, fontSize: 14, lineHeight: 1.6 }}>
                <span style={{ color: 'var(--accent3)', flexShrink: 0 }}>+</span>{p.point}
              </div>
            ))}
          </div>
          <div style={card({ borderLeft: '3px solid var(--danger)' })}>
            <div style={{ fontSize: 11, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--danger)', marginBottom: 12 }}>Focus areas</div>
            {(analysis.gaps || []).map((g, i) => (
              <div key={i} style={{ display: 'flex', gap: 10, marginBottom: 10, fontSize: 14, lineHeight: 1.6 }}>
                <span style={{ color: 'var(--danger)', flexShrink: 0 }}>−</span>{g.point}
              </div>
            ))}
          </div>
        </div>
      )}
      <RoadmapProgress roadmap={roadmap} currentWeek={currentWeek} />
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 32 }}>
        <Btn onClick={onStart} disabled={loading}>
          {loading ? <><Spinner size={16} /> Generating…</> : 'Start Week 1 →'}
        </Btn>
      </div>
    </div>
  )
}

// ── WeeklyPhase ───────────────────────────────────────────────────────────────

function WeeklyPhase({ sessionId, state, roadmap, onNextWeek, onComplete }) {
  const [tasks,       setTasks]       = useState(null)
  const [checkResult, setCheckResult] = useState(null)
  const [quiz,        setQuiz]        = useState(null)
  const [answers,     setAnswers]     = useState({})
  const [quizGraded,  setQuizGraded]  = useState(false)
  const [evaluation,  setEvaluation]  = useState(null)
  const [loading,     setLoading]     = useState(false)
  const [error,       setError]       = useState('')

  const curWeek  = state?.current_week || 1
  const weekPlan = roadmap?.weeks?.[curWeek - 1]
  const DIFF_COLOR = { easy: 'var(--accent3)', medium: 'var(--accent2)', hard: 'var(--danger)' }
  const DIFF_BG    = { easy: 'rgba(61,217,164,0.15)', medium: 'rgba(240,165,0,0.15)', hard: 'rgba(240,93,93,0.15)' }

  async function loadTasks() {
    if (!sessionId) return
    setLoading(true); setError('')
    try {
      const res = await api.startWeek(sessionId)
      setTasks(res.tasks)
    } catch (e) { setError(e.message) }
    setLoading(false)
  }

  useEffect(() => { if (sessionId) loadTasks() }, [sessionId])

  async function check() {
    setLoading(true); setError('')
    try {
      const res = await api.checkCompletion(sessionId)
      setCheckResult(res)
    } catch (e) { setError(e.message) }
    setLoading(false)
  }

  async function loadQuiz() {
    setLoading(true); setError('')
    try {
      const res = await api.getTaskQuiz(sessionId)
      setQuiz(res); setAnswers({}); setQuizGraded(false)
    } catch (e) { setError(e.message) }
    setLoading(false)
  }

  async function submitQuiz() {
    if (!quiz) return
    const ans = quiz.questions.map((_, i) => answers[i] || '')
    setLoading(true); setError('')
    try {
      const res = await api.submitTaskQuiz(sessionId, ans)
      setEvaluation(res); setQuizGraded(true)
      if (res.project_complete) onComplete(res)
    } catch (e) { setError(e.message) }
    setLoading(false)
  }

  return (
    <div className="fade-up">
      <Eyebrow>Week {curWeek} of {roadmap?.total_weeks || '?'}</Eyebrow>
      <H1>{weekPlan?.theme || 'This week'}</H1>
      <p style={{ color: 'var(--muted)', fontSize: 14, marginBottom: 8, lineHeight: 1.6 }}>{weekPlan?.goal}</p>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center', marginBottom: 32 }}>
        <span style={{ fontSize: 10, letterSpacing: '0.1em', textTransform: 'uppercase', padding: '3px 10px', borderRadius: 20, fontWeight: 500, background: DIFF_BG[weekPlan?.difficulty] || DIFF_BG.medium, color: DIFF_COLOR[weekPlan?.difficulty] || DIFF_COLOR.medium }}>
          {weekPlan?.difficulty}
        </span>
        {(weekPlan?.topics || []).map((t, i) => (
          <span key={i} style={{ fontSize: 11, background: 'var(--surface2)', border: '1px solid var(--border)', borderRadius: 6, padding: '3px 10px', color: 'var(--muted)' }}>{t}</span>
        ))}
      </div>

      {loading && !tasks
        ? <div style={{ display: 'flex', justifyContent: 'center', padding: 48 }}><Spinner size={32} /></div>
        : tasks && tasks.map(t => <TaskCard key={t.day} task={t} />)
      }

      {tasks && (
        <>
          <div style={{ height: 1, background: 'var(--border)', margin: '28px 0' }} />
          {!checkResult
            ? <div style={card({ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 16 })}>
                <div>
                  <H2>Completion check</H2>
                  <p style={{ fontSize: 13, color: 'var(--muted)' }}>Push your work to GitHub first, then run the check.</p>
                </div>
                <Btn variant="outline" onClick={check} disabled={loading}>
                  {loading ? <><Spinner size={16} /> Checking…</> : 'Check GitHub →'}
                </Btn>
              </div>
            : <div style={card({ borderLeft: `3px solid ${checkResult.completed ? 'var(--accent3)' : 'var(--danger)'}` })}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
                  <H2>{checkResult.completed ? '✓ Deliverable found' : '✗ Not found yet'}</H2>
                  <span style={{ fontSize: 11, padding: '4px 12px', borderRadius: 20, background: checkResult.completed ? 'rgba(61,217,164,0.15)' : 'rgba(240,93,93,0.15)', color: checkResult.completed ? 'var(--accent3)' : 'var(--danger)' }}>
                    {checkResult.completed ? 'DONE' : 'NOT DONE'}
                  </span>
                </div>
                <p style={{ fontSize: 13, color: 'var(--muted)', lineHeight: 1.6 }}>{checkResult.reason}</p>
                {!checkResult.completed && <div style={{ marginTop: 12 }}><Btn variant="outline" small onClick={check}>Re-check →</Btn></div>}
              </div>
          }

          {checkResult?.completed && !quiz && !evaluation && (
            <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 16 }}>
              <Btn onClick={loadQuiz} disabled={loading}>{loading ? <><Spinner size={16} /></> : 'Take the quiz →'}</Btn>
            </div>
          )}

          {quiz && !evaluation && (
            <>
              <div style={{ height: 1, background: 'var(--border)', margin: '28px 0' }} />
              <H2>Weekly quiz</H2>
              <p style={{ fontSize: 13, color: 'var(--muted)', marginBottom: 24 }}>Based on what you built this week.</p>
              {quiz.questions.map((q, i) => (
                <QuestionCard key={i} q={q} index={i} answers={answers} setAnswers={setAnswers} graded={quizGraded} />
              ))}
              <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 24 }}>
                <Btn onClick={submitQuiz} disabled={loading}>
                  {loading ? <><Spinner size={16} /> Evaluating…</> : 'Submit & get score →'}
                </Btn>
              </div>
            </>
          )}

          {evaluation && (
            <>
              <div style={{ height: 1, background: 'var(--border)', margin: '28px 0' }} />
              <div style={card({ textAlign: 'center', padding: '40px 28px' })}>
                <Eyebrow>Week {evaluation.week_number} evaluation</Eyebrow>
                <div style={{ display: 'flex', justifyContent: 'center', margin: '20px 0' }}>
                  <ScoreRing score={evaluation.score} display={evaluation.score_display} />
                </div>
                <p style={{ fontSize: 13, color: 'var(--muted)', marginBottom: 24 }}>{evaluation.feedback?.message}</p>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, textAlign: 'left', marginBottom: 16 }}>
                  <div>
                    <div style={{ fontSize: 11, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--muted)', marginBottom: 8 }}>Strength</div>
                    <div style={{ fontSize: 14, lineHeight: 1.7 }}>{evaluation.feedback?.strength}</div>
                  </div>
                  <div>
                    <div style={{ fontSize: 11, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--muted)', marginBottom: 8 }}>Improve</div>
                    <div style={{ fontSize: 14, lineHeight: 1.7 }}>{evaluation.feedback?.improvement}</div>
                  </div>
                </div>
                <div style={card({ borderLeft: '3px solid var(--accent2)', textAlign: 'left' })}>
                  <div style={{ fontSize: 11, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--muted)', marginBottom: 8 }}>Next week tip</div>
                  <div style={{ fontSize: 14, lineHeight: 1.7 }}>{evaluation.feedback?.next_week_tip}</div>
                </div>
                {!evaluation.project_complete && (
                  <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 24 }}>
                    <Btn variant="green" onClick={() => onNextWeek(evaluation)}>
                      {loading ? <><Spinner size={16} /></> : `Start Week ${curWeek + 1} →`}
                    </Btn>
                  </div>
                )}
              </div>
            </>
          )}
        </>
      )}

      {error && <div style={card({ borderLeft: '3px solid var(--danger)', marginTop: 16 })}><span style={{ color: 'var(--danger)', fontSize: 14 }}>{error}</span></div>}
    </div>
  )
}

// ── MAIN PAGE ─────────────────────────────────────────────────────────────────

const PHASE_IDX = { prereq: 1, approach: 2, roadmap: 3, weekly: 4, complete: 5 }

export default function ProjectPage() {
  const router      = useRouter()
  const [sessionId, setSessionId] = useState(null)
  const [state,     setState]     = useState(null)
  const [phase,     setPhase]     = useState('prereq')
  const [roadmap,   setRoadmap]   = useState(null)
  const [analysis,  setAnalysis]  = useState(null)
  const [loading,   setLoading]   = useState(false)
  const [finalEval, setFinalEval] = useState(null)

  useEffect(() => {
    const sid = sessionStorage.getItem('sessionId')
    if (!sid) { router.push('/'); return }
    async function load() {
      try {
        const data = await api.getSession(sid)
        setSessionId(sid)
        setState(data)
      } catch {
        router.push('/')
      }
    }
    load()
  }, [router])

  async function refreshState() {
    const fresh = await api.getSession(sessionId)
    setState(fresh)
    return fresh
  }

  // ── Prereq done handler ─────────────────────────────────────────────────────
  // signal === 'approach'  → all prereqs done, switch phase
  // signal === 'refresh'   → next concept loaded, stay on prereq
  //   newState is the already-mutated local state from PrereqPhase;
  //   we update parent state so the prop stays in sync, but PrereqPhase
  //   drives its own display from localState — the parent update is
  //   just for persistence (approach phase needs full prereqs list etc.)
  function onPrereqDone(signal, newState) {
    if (signal === 'approach') {
      setPhase('approach')
    } else if (signal === 'refresh') {
      setState(newState)
      // Safety: if for any reason index >= total, push to approach
      if (newState.current_concept_index >= (newState.prerequisites?.length ?? 0)) {
        setPhase('approach')
      }
    }
  }

  function onApproachDone(res) {
    setAnalysis(res.analysis)
    setRoadmap(res.roadmap)
    refreshState()
    setPhase('roadmap')
  }

  async function onStartWeek() {
    setLoading(true)
    try { await refreshState(); setPhase('weekly') }
    catch (e) { console.error(e) }
    setLoading(false)
  }

  async function onNextWeek() {
    const fresh = await refreshState()
    setState(fresh)
    setPhase('weekly')
  }

  function onComplete(ev) {
    setFinalEval(ev)
    setPhase('complete')
  }

  if (!state) return (
    <div style={{ display: 'flex', height: '100vh', alignItems: 'center', justifyContent: 'center' }}>
      <Spinner size={40} />
    </div>
  )

  return (
    <div style={{ display: 'flex', minHeight: '100vh' }}>
      <Sidebar role="student" />
      <main style={{ flex: 1, padding: '40px 48px', overflowY: 'auto' }}>
        <PhaseProgress activeIndex={PHASE_IDX[phase] || 1} />
        <div style={{ marginTop: 40 }}>

          {phase === 'prereq' && (
            <PrereqPhase sessionId={sessionId} state={state} onDone={onPrereqDone} />
          )}

          {phase === 'approach' && (
            <ApproachPhase sessionId={sessionId} state={state} onDone={onApproachDone} />
          )}

          {phase === 'roadmap' && roadmap && (
            <RoadmapPhase roadmap={roadmap} analysis={analysis} currentWeek={state?.current_week || 1} onStart={onStartWeek} loading={loading} />
          )}

          {phase === 'weekly' && (
            <WeeklyPhase sessionId={sessionId} state={state} roadmap={roadmap} onNextWeek={onNextWeek} onComplete={onComplete} />
          )}

          {phase === 'complete' && (
            <div className="fade-up" style={{ textAlign: 'center', paddingTop: 60 }}>
              <Eyebrow>Project complete</Eyebrow>
              <H1>You built it.<br /><span style={{ color: 'var(--accent3)' }}>Well done.</span></H1>
              <p style={{ fontFamily: 'var(--font-serif)', fontStyle: 'italic', color: 'var(--muted)', fontSize: 20, marginBottom: 48 }}>
                Evaluated across all {roadmap?.total_weeks} weeks.
              </p>
              <div style={{ ...card(), maxWidth: 360, margin: '0 auto 32px' }}>
                <div style={{ fontSize: 11, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--muted)', marginBottom: 12 }}>Final score</div>
                <div style={{ fontFamily: 'var(--font-head)', fontSize: 64, fontWeight: 800, color: 'var(--accent3)', lineHeight: 1 }}>
                  {finalEval?.score_display || '—'}<span style={{ fontSize: 24, color: 'var(--muted)' }}>/10</span>
                </div>
              </div>
              <button onClick={() => router.push('/')} style={{ display: 'inline-flex', alignItems: 'center', gap: 8, padding: '12px 24px', borderRadius: 8, border: '1px solid var(--border)', background: 'transparent', color: 'var(--text)', fontFamily: 'var(--font-mono)', fontSize: 14, cursor: 'pointer' }}>
                Start new session
              </button>
            </div>
          )}

        </div>
      </main>
    </div>
  )
}