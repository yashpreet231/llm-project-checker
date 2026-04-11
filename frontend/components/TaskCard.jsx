'use client'

export default function TaskCard({ task }) {
  return (
    <div style={{
      background: 'var(--surface2)',
      border: '1px solid var(--border)',
      borderRadius: 10,
      padding: 20,
      marginBottom: 12,
    }}>
      {/* header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12 }}>
        <div style={{
          width: 32, height: 32, borderRadius: 8,
          background: 'var(--surface)',
          border: '1px solid var(--border)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: 12, color: 'var(--muted)', fontWeight: 500, flexShrink: 0,
        }}>
          D{task.day}
        </div>
        <div style={{
          fontFamily: 'var(--font-head)',
          fontSize: 15, fontWeight: 700, flex: 1,
        }}>
          {task.title}
        </div>
        <div style={{ fontSize: 11, color: 'var(--muted)', whiteSpace: 'nowrap' }}>
          {task.estimated_hours}h
        </div>
      </div>

      {/* description */}
      <p style={{ fontSize: 13, color: 'var(--muted)', lineHeight: 1.6, marginBottom: 12 }}>
        {task.description}
      </p>

      {/* steps */}
      <ul style={{ listStyle: 'none', marginBottom: 12 }}>
        {task.steps.map((step, i) => (
          <li key={i} style={{
            display: 'flex', gap: 10, fontSize: 13,
            color: 'var(--muted)', marginBottom: 8, lineHeight: 1.5,
          }}>
            <span style={{ color: 'var(--accent)', flexShrink: 0 }}>→</span>
            {step}
          </li>
        ))}
      </ul>

      {/* commit tag */}
      <div style={{
        display: 'inline-flex', alignItems: 'center', gap: 6,
        fontSize: 11, color: 'var(--accent2)',
        background: 'rgba(240,165,0,0.08)',
        border: '1px solid rgba(240,165,0,0.2)',
        borderRadius: 6, padding: '4px 10px',
      }}>
        <span>📁</span>
        <span>{task.submission.github_folder}/{task.submission.filename}</span>
        <span style={{ color: 'var(--muted)' }}>·</span>
        <span style={{ fontStyle: 'italic' }}>{task.submission.commit_message}</span>
      </div>
    </div>
  )
}