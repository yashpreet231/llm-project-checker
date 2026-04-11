'use client'
import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { startSession } from '@/lib/api'
import { PhaseProgress, Spinner } from '@/components/ProgressAnimation'

function TagInput({ tags, onAdd, onRemove, placeholder, variant }) {
  const [val, setVal] = useState('')

  const color = variant === 'known' ? 'var(--accent3)' : 'var(--accent2)'
  const borderColor =
    variant === 'known'
      ? 'rgba(61,217,164,0.3)'
      : 'rgba(240,165,0,0.3)'

  const add = () => {
    const v = val.trim()
    if (v && !tags.includes(v)) onAdd(v)
    setVal('')
  }

  return (
    <div
      style={{
        display: 'flex',
        flexWrap: 'wrap',
        gap: 8,
        background: 'var(--surface2)',
        border: '1px solid var(--border)',
        borderRadius: 8,
        padding: 10,
        minHeight: 48,
      }}
    >
      {tags.map((t) => (
        <span
          key={t}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 6,
            background: 'var(--surface)',
            border: `1px solid ${borderColor}`,
            borderRadius: 6,
            padding: '4px 10px',
            fontSize: 13,
            color,
          }}
        >
          {t}
          <button
            onClick={() => onRemove(t)}
            style={{
              background: 'none',
              border: 'none',
              color: 'inherit',
              cursor: 'pointer',
              fontSize: 14,
              lineHeight: 1,
              opacity: 0.6,
            }}
          >
            ×
          </button>
        </span>
      ))}

      <input
        value={val}
        onChange={(e) => setVal(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter') {
            e.preventDefault()
            add()
          }
        }}
        placeholder={placeholder}
        style={{
          background: 'none',
          border: 'none',
          outline: 'none',
          color: 'var(--text)',
          fontFamily: 'var(--font-mono)',
          fontSize: 13,
          minWidth: 100,
          flex: 1,
        }}
      />
    </div>
  )
}

export default function HomePage() {
  const router = useRouter()

  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const [userId, setUserId] = useState('')
  const [projectName, setProjectName] = useState('')
  const [projectDesc, setProjectDesc] = useState('')
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')
  const [repoUrl, setRepoUrl] = useState('')
  const [branch, setBranch] = useState('main')
  const [known, setKnown] = useState([])
  const [unknown, setUnknown] = useState([])

  async function handleStart() {
    setError('')

    if (
      !userId ||
      !projectName ||
      !projectDesc ||
      !startDate ||
      !endDate ||
      !repoUrl
    ) {
      setError('Please fill in all fields.')
      return
    }

    if (!unknown.length) {
      setError('Add at least one unknown tech stack item.')
      return
    }

    setLoading(true)

    try {
      const res = await startSession({
        user_id: userId,
        project: {
          name: projectName,
          description: projectDesc,
        },
        known_stack: known,
        unknown_stack: unknown,
        start_date: startDate,
        end_date: endDate,
        repo_url: repoUrl,
        github_branch: branch || 'main',
      })

      sessionStorage.setItem('sessionId', res.session_id)
      sessionStorage.setItem('totalConcepts', res.total_concepts)

      router.push('/project')
    } catch (e) {
      setError(e.message || 'Something went wrong')
    }

    setLoading(false)
  }

  return (
    <div style={{ maxWidth: 860, margin: '0 auto', padding: '40px 24px' }}>
      <PhaseProgress activeIndex={0} />

      <div style={{ marginTop: 40 }}>
        <h1>Configure your project</h1>

        <input
          placeholder="Student ID"
          value={userId}
          onChange={(e) => setUserId(e.target.value)}
        />

        <input
          placeholder="Project Name"
          value={projectName}
          onChange={(e) => setProjectName(e.target.value)}
        />

        <textarea
          placeholder="Project Description"
          value={projectDesc}
          onChange={(e) => setProjectDesc(e.target.value)}
        />

        <TagInput
          tags={known}
          onAdd={(v) => setKnown([...known, v])}
          onRemove={(v) => setKnown(known.filter((t) => t !== v))}
          placeholder="Known tech"
          variant="known"
        />

        <TagInput
          tags={unknown}
          onAdd={(v) => setUnknown([...unknown, v])}
          onRemove={(v) => setUnknown(unknown.filter((t) => t !== v))}
          placeholder="Unknown tech"
          variant="unknown"
        />

        <input
          type="date"
          value={startDate}
          onChange={(e) => setStartDate(e.target.value)}
        />

        <input
          type="date"
          value={endDate}
          onChange={(e) => setEndDate(e.target.value)}
        />

        <input
          placeholder="Repo URL"
          value={repoUrl}
          onChange={(e) => setRepoUrl(e.target.value)}
        />

        <button onClick={handleStart} disabled={loading}>
          {loading ? <Spinner size={18} /> : 'Start Session'}
        </button>

        {error && <p style={{ color: 'red' }}>{error}</p>}
      </div>
    </div>
  )
}