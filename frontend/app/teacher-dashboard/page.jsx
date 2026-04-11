'use client'
import { useState } from 'react'
import Sidebar from '@/components/Sidebar'
import { Spinner } from '@/components/ProgressAnimation'
import * as api from '@/lib/api'

function TagInput({ tags, onAdd, onRemove, placeholder, variant }) {
  const [val, setVal] = useState('')
  const color = variant === 'known' ? 'var(--accent3)' : 'var(--accent2)'
  const borderColor = variant === 'known'
    ? 'rgba(61,217,164,0.3)'
    : 'rgba(240,165,0,0.3)'

  const add = () => {
    const v = val.trim()
    if (v && !tags.includes(v)) onAdd(v)
    setVal('')
  }

  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, background: 'var(--surface2)', border: '1px solid var(--border)', borderRadius: 8, padding: 10, minHeight: 48 }}>
      {tags.map(t => (
        <span key={t} style={{ display: 'flex', alignItems: 'center', gap: 6, background: 'var(--surface)', border: `1px solid ${borderColor}`, borderRadius: 6, padding: '4px 10px', fontSize: 13, color }}>
          {t}
          <button onClick={() => onRemove(t)} style={{ background: 'none', border: 'none', color: 'inherit', cursor: 'pointer', fontSize: 14, opacity: 0.6 }}>
            ×
          </button>
        </span>
      ))}
      <input
        value={val}
        onChange={e => setVal(e.target.value)}
        onKeyDown={e => e.key === 'Enter' && (e.preventDefault(), add())}
        placeholder={placeholder}
        style={{ background: 'none', border: 'none', outline: 'none', color: 'var(--text)', fontFamily: 'var(--font-mono)', fontSize: 13, minWidth: 100, flex: 1 }}
      />
    </div>
  )
}

export default function TeacherDashboard() {
  const [loading, setLoading] = useState(false)
  const [success, setSuccess] = useState('')
  const [error, setError] = useState('')

  const [name, setName] = useState('')
  const [desc, setDesc] = useState('')
  const [stack, setStack] = useState([])

  const inp = {
    width: '100%',
    background: 'var(--surface2)',
    border: '1px solid var(--border)',
    borderRadius: 8,
    padding: '12px 14px',
    color: 'var(--text)',
    fontFamily: 'var(--font-mono)',
    fontSize: 14,
    outline: 'none'
  }

  const card = (extra = {}) => ({
    background: 'var(--surface)',
    border: '1px solid var(--border)',
    borderRadius: 12,
    padding: 28,
    marginBottom: 16,
    ...extra
  })

  async function handleCreate() {
    if (!name || !desc || !stack.length) {
      setError('Fill in all fields.')
      return
    }

    setLoading(true)
    setError('')
    setSuccess('')

    try {
      await api.createProject({
        name,
        description: desc,
        tech_stack: stack
      })

      setSuccess(`Project "${name}" created successfully.`)
      setName('')
      setDesc('')
      setStack([])
    } catch (e) {
      setError(e.message)
    }

    setLoading(false)
  }

  return (
    <div style={{ display: 'flex', minHeight: '100vh' }}>
      <Sidebar role="teacher" />

      <main style={{ flex: 1, padding: '40px 48px', overflowY: 'auto' }}>
        <div style={{ marginBottom: 40 }}>
          <div style={{ fontSize: 11, letterSpacing: '0.15em', textTransform: 'uppercase', color: 'var(--accent2)', marginBottom: 12 }}>
            Teacher dashboard
          </div>

          <h1 style={{ fontFamily: 'var(--font-head)', fontSize: 'clamp(28px,4vw,44px)', fontWeight: 800, lineHeight: 1.05, letterSpacing: '-1px' }}>
            Assign a project.
          </h1>
        </div>

        <div style={card()}>
          <div style={{ fontFamily: 'var(--font-head)', fontSize: 20, fontWeight: 700, marginBottom: 24 }}>
            New project
          </div>

          <div style={{ marginBottom: 20 }}>
            <label style={{ fontSize: 11, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--muted)', marginBottom: 8, display: 'block' }}>
              Project name
            </label>
            <input
              style={inp}
              value={name}
              onChange={e => setName(e.target.value)}
              placeholder="AI Task Manager"
            />
          </div>

          <div style={{ marginBottom: 20 }}>
            <label style={{ fontSize: 11, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--muted)', marginBottom: 8, display: 'block' }}>
              Description
            </label>
            <textarea
              style={{ ...inp, minHeight: 100, resize: 'vertical', lineHeight: 1.6 }}
              value={desc}
              onChange={e => setDesc(e.target.value)}
              placeholder="Describe what the student will build and what technologies to use…"
            />
          </div>

          <div style={{ marginBottom: 24 }}>
            <label style={{ fontSize: 11, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--muted)', marginBottom: 8, display: 'block' }}>
              Required tech stack <span style={{ color: 'var(--accent2)' }}>(press Enter)</span>
            </label>

            <TagInput
              tags={stack}
              onAdd={v => setStack(p => [...p, v])}
              onRemove={v => setStack(p => p.filter(t => t !== v))}
              placeholder="React, FastAPI, Docker…"
              variant="unknown"
            />
          </div>

          {error && (
            <div style={{ ...card({ borderLeft: '3px solid var(--danger)', marginBottom: 16 }) }}>
              <span style={{ color: 'var(--danger)', fontSize: 14 }}>{error}</span>
            </div>
          )}

          {success && (
            <div style={{ ...card({ borderLeft: '3px solid var(--accent3)', marginBottom: 16 }) }}>
              <span style={{ color: 'var(--accent3)', fontSize: 14 }}>{success}</span>
            </div>
          )}

          <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
            <button
              onClick={handleCreate}
              disabled={loading}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 8,
                padding: '12px 24px',
                borderRadius: 8,
                border: 'none',
                background: 'var(--accent2)',
                color: '#0a0a0f',
                fontFamily: 'var(--font-mono)',
                fontSize: 14,
                fontWeight: 500,
                cursor: loading ? 'not-allowed' : 'pointer',
                opacity: loading ? 0.6 : 1,
              }}
            >
              {loading ? (
                <>
                  <Spinner size={16} /> Creating…
                </>
              ) : (
                'Create project →'
              )}
            </button>
          </div>
        </div>

        <div style={{ ...card(), borderStyle: 'dashed', opacity: 0.5, textAlign: 'center', padding: 40 }}>
          <div style={{ fontSize: 14, color: 'var(--muted)' }}>
            Assigned projects will appear here once your backend connects the GET /projects endpoint.
          </div>
        </div>
      </main>
    </div>
  )
}