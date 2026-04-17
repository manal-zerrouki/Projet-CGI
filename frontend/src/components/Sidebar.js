import { useState } from 'react'
import { LayoutDashboard, FileText, Clock, Building2, Menu } from 'lucide-react'

const navItems = [
  { id: 'dashboard',    label: 'Tableau de bord', Icon: LayoutDashboard },
  { id: 'factures',     label: 'Factures',         Icon: FileText        },
  { id: 'historique',   label: 'Historique',       Icon: Clock           },
  { id: 'fournisseurs', label: 'Fournisseurs',     Icon: Building2       },
]

export default function Sidebar({ activePage, setActivePage, lastResult }) {
  const [open, setOpen] = useState(true)

  const statusDot =
    lastResult?.validation === 'accepté'              ? '#4ade80' :
    lastResult?.validation === 'accepté_avec_réserve' ? '#facc15' :
    lastResult?.validation === 'rejeté'               ? '#f87171' : null

  return (
    <aside style={{
      width: open ? 256 : 68,
      minHeight: '100vh',
      transition: 'width 0.25s ease',
      flexShrink: 0,
      display: 'flex',
      flexDirection: 'column',
      backgroundColor: '#1e3a8a',
      color: 'white',
      overflow: 'hidden',
    }}>

      {/* ── Header ── */}
      <div style={{
        height: 72,
        display: 'flex',
        alignItems: 'center',
        borderBottom: '1px solid rgba(255,255,255,0.1)',
        flexShrink: 0,
        padding: open ? '0 14px' : '0',
        justifyContent: open ? 'flex-start' : 'center',
        gap: 10,
        transition: 'padding 0.25s ease',
      }}>
        {/* Quand ouvert : logo + titre + bouton */}
        {open ? (
          <>
            <img
              src="/CGI_logo.jpg"
              alt="CGI"
              style={{ width: 40, height: 40, borderRadius: 8, objectFit: 'cover', flexShrink: 0 }}
            />
            <div style={{ flex: 1, overflow: 'hidden' }}>
              <p style={{ fontSize: 12, color: '#93c5fd', whiteSpace: 'normal', lineHeight: 1.3 }}>Système de Validation des Factures</p>
            </div>
            <button
              onClick={() => setOpen(false)}
              title="Réduire"
              style={{
                flexShrink: 0, width: 32, height: 32, borderRadius: 6,
                border: '1.5px solid rgba(255,255,255,0.4)',
                background: 'rgba(255,255,255,0.15)',
                cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center',
                color: 'white', transition: 'background 0.15s',
              }}
              onMouseEnter={e => e.currentTarget.style.background = 'rgba(255,255,255,0.3)'}
              onMouseLeave={e => e.currentTarget.style.background = 'rgba(255,255,255,0.15)'}
            >
              <Menu size={16} color="white" />
            </button>
          </>
        ) : (
          /* Quand fermé : UNIQUEMENT le bouton, centré */
          <button
            onClick={() => setOpen(true)}
            title="Agrandir"
            style={{
              width: 40, height: 40, borderRadius: 8,
              border: '1.5px solid rgba(255,255,255,0.4)',
              background: 'rgba(255,255,255,0.15)',
              cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center',
              color: 'white', transition: 'background 0.15s',
            }}
            onMouseEnter={e => e.currentTarget.style.background = 'rgba(255,255,255,0.3)'}
            onMouseLeave={e => e.currentTarget.style.background = 'rgba(255,255,255,0.15)'}
          >
            <Menu size={18} color="white" />
          </button>
        )}
      </div>

      {/* ── Navigation ── */}
      <nav style={{ flex: 1, padding: '12px 8px', display: 'flex', flexDirection: 'column', gap: 2 }}>
        {navItems.map(({ id, label, Icon }) => {
          const isActive = activePage === id
          return (
            <button
              key={id}
              onClick={() => setActivePage(id)}
              title={!open ? label : undefined}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 10,
                justifyContent: open ? 'flex-start' : 'center',
                padding: '10px 12px',
                borderRadius: 8,
                border: 'none',
                cursor: 'pointer',
                fontSize: 14,
                fontWeight: isActive ? 600 : 400,
                background: isActive ? '#2563eb' : 'transparent',
                color: isActive ? 'white' : '#93c5fd',
                width: '100%',
                textAlign: 'left',
                position: 'relative',
                transition: 'background 0.15s, color 0.15s',
              }}
              onMouseEnter={e => { if (!isActive) { e.currentTarget.style.background = 'rgba(255,255,255,0.1)'; e.currentTarget.style.color = 'white' } }}
              onMouseLeave={e => { if (!isActive) { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.color = '#93c5fd' } }}
            >
              <Icon size={18} style={{ flexShrink: 0 }} />
              <span style={{
                whiteSpace: 'nowrap',
                overflow: 'hidden',
                opacity: open ? 1 : 0,
                maxWidth: open ? 160 : 0,
                transition: 'opacity 0.2s ease, max-width 0.25s ease',
              }}>
                {label}
              </span>

              {/* Dot statut sur Factures */}
              {id === 'factures' && statusDot && (
                <span style={{
                  position: 'absolute',
                  top: 8, right: 8,
                  width: 8, height: 8,
                  borderRadius: '50%',
                  background: statusDot,
                  flexShrink: 0,
                }} />
              )}
            </button>
          )
        })}
      </nav>

      {/* ── Footer ── */}
      <div style={{
        borderTop: '1px solid rgba(255,255,255,0.1)',
        padding: '12px 16px',
        flexShrink: 0,
        overflow: 'hidden',
        opacity: open ? 1 : 0,
        maxHeight: open ? 40 : 0,
        transition: 'opacity 0.2s ease, max-height 0.25s ease',
      }}>
        <p style={{ fontSize: 11, color: '#3b82f6', whiteSpace: 'nowrap' }}>Système interne CGI</p>
      </div>
    </aside>
  )
}
