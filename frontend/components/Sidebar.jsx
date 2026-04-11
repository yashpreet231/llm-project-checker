'use client'
import Link from 'next/link'
import { usePathname } from 'next/navigation'

const studentLinks = [
  { href: '/student-dashboard', label: 'Dashboard',   icon: '⬡' },
  { href: '/project',           label: 'My project',  icon: '◈' },
]

const teacherLinks = [
  { href: '/teacher-dashboard', label: 'Overview',    icon: '⬡' },
]

export default function Sidebar({ role = 'student' }) {
  const pathname = usePathname()
  const links = role === 'teacher' ? teacherLinks : studentLinks

  return (
    <aside style={{
      width: 220,
      minHeight: '100vh',
      background: 'var(--surface)',
      borderRight: '1px solid var(--border)',
      display: 'flex',
      flexDirection: 'column',
      padding: '32px 20px',
      flexShrink: 0,
    }}>
      {/* logo */}
      <div style={{
        fontFamily: 'var(--font-head)',
        fontSize: 20,
        fontWeight: 800,
        letterSpacing: '-0.5px',
        marginBottom: 48,
      }}>
        ai<span style={{ color: 'var(--accent)' }}>teacher</span>
      </div>

      {/* role pill */}
      <div style={{
        fontSize: 10,
        letterSpacing: '0.12em',
        textTransform: 'uppercase',
        color: role === 'teacher' ? 'var(--accent2)' : 'var(--accent3)',
        background: role === 'teacher' ? 'rgba(240,165,0,0.1)' : 'rgba(61,217,164,0.1)',
        border: `1px solid ${role === 'teacher' ? 'rgba(240,165,0,0.2)' : 'rgba(61,217,164,0.2)'}`,
        borderRadius: 20,
        padding: '4px 12px',
        display: 'inline-block',
        marginBottom: 32,
      }}>
        {role}
      </div>

      {/* nav links */}
      <nav style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
        {links.map(({ href, label, icon }) => {
          const active = pathname === href
          return (
            <Link key={href} href={href} style={{
              display: 'flex',
              alignItems: 'center',
              gap: 10,
              padding: '10px 14px',
              borderRadius: 8,
              fontSize: 14,
              color: active ? 'var(--text)' : 'var(--muted)',
              background: active ? 'var(--surface2)' : 'transparent',
              border: active ? '1px solid var(--border)' : '1px solid transparent',
              textDecoration: 'none',
              transition: 'all 0.2s',
            }}>
              <span style={{ fontSize: 16 }}>{icon}</span>
              {label}
            </Link>
          )
        })}
      </nav>

      {/* bottom spacer */}
      <div style={{ flex: 1 }} />
      <div style={{ fontSize: 12, color: 'var(--muted)', lineHeight: 1.5 }}>
        AI Teacher Agent<br/>
        <span style={{ color: 'var(--border)' }}>v1.0.0</span>
      </div>
    </aside>
  )
}
