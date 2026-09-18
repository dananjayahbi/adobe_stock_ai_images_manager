import { useMemo, useState } from 'react'
import {
  AlertTriangle,
  Archive,
  ArrowUpRight,
  Check,
  CheckCircle2,
  ChevronDown,
  CircleHelp,
  Clock3,
  CloudOff,
  FileCheck2,
  Filter,
  FolderOpen,
  Gauge,
  Grid2X2,
  Image as ImageIcon,
  LayoutDashboard,
  ListFilter,
  MoreHorizontal,
  PanelLeft,
  RefreshCw,
  Search,
  Settings2,
  ShieldCheck,
  Sparkles,
  Upload,
  XCircle,
} from 'lucide-react'

type AssetStatus = 'Review needed' | 'Ready' | 'Processing' | 'Blocked'
type Asset = {
  id: string
  name: string
  type: string
  status: AssetStatus
  risk: 'Low' | 'Medium' | 'High'
  issue: string
  time: string
  image: string
}

const assets: Asset[] = [
  {
    id: 'AS-2048',
    name: 'botanical-glasshouse.jpg',
    type: 'AI generated',
    status: 'Review needed',
    risk: 'Medium',
    issue: 'Text-like artifact detected',
    time: '14 min ago',
    image: 'linear-gradient(135deg, #d5e5db 0%, #6b8f7b 48%, #1d3d35 100%)',
  },
  {
    id: 'AS-2047',
    name: 'desert-architecture.jpg',
    type: 'AI generated',
    status: 'Ready',
    risk: 'Low',
    issue: 'All checks verified',
    time: '22 min ago',
    image: 'linear-gradient(135deg, #efd4a5 0%, #bb805a 47%, #492b29 100%)',
  },
  {
    id: 'AS-2046',
    name: 'quiet-ocean-study.jpg',
    type: 'AI generated',
    status: 'Processing',
    risk: 'Low',
    issue: 'Semantic audit in progress',
    time: '28 min ago',
    image: 'linear-gradient(140deg, #d5e8e9 0%, #6f9fac 47%, #27495b 100%)',
  },
  {
    id: 'AS-2045',
    name: 'neon-market-night.jpg',
    type: 'AI generated',
    status: 'Blocked',
    risk: 'High',
    issue: 'Logo-like mark needs inspection',
    time: '41 min ago',
    image: 'linear-gradient(140deg, #ffc988 0%, #d86d81 43%, #392a55 100%)',
  },
]

const navItems = [
  { label: 'Overview', icon: LayoutDashboard },
  { label: 'Review queue', icon: ListFilter, count: 12 },
  { label: 'Batches', icon: Archive },
  { label: 'Ready to upload', icon: FileCheck2, count: 8 },
]

function StatusBadge({ status }: { status: AssetStatus }) {
  const Icon = status === 'Ready' ? CheckCircle2 : status === 'Blocked' ? XCircle : status === 'Processing' ? Clock3 : AlertTriangle
  return <span className={`status status-${status.toLowerCase().replace(' ', '-')}`}><Icon size={13} aria-hidden="true" />{status}</span>
}

function Risk({ level }: { level: Asset['risk'] }) {
  return <span className={`risk risk-${level.toLowerCase()}`}><span aria-hidden="true" />{level} risk</span>
}

function App() {
  const [activeNav, setActiveNav] = useState('Review queue')
  const [filter, setFilter] = useState<'All' | AssetStatus>('All')
  const [selectedId, setSelectedId] = useState('AS-2048')
  const [search, setSearch] = useState('')
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [reviewed, setReviewed] = useState(false)

  const filteredAssets = useMemo(() => assets.filter((asset) => {
    const matchesFilter = filter === 'All' || asset.status === filter
    const matchesSearch = `${asset.name} ${asset.id}`.toLowerCase().includes(search.toLowerCase())
    return matchesFilter && matchesSearch
  }), [filter, search])
  const selected = assets.find((asset) => asset.id === selectedId) ?? assets[0]

  return (
    <div className="app-shell">
      <aside className={`sidebar ${sidebarOpen ? '' : 'sidebar-collapsed'}`}>
        <div className="brand">
          <div className="brand-mark"><Sparkles size={16} strokeWidth={2.5} /></div>
          {sidebarOpen && <div><strong>Image Studio</strong><span>LOCAL REVIEW WORKSPACE</span></div>}
        </div>
        <div className="workspace-label">WORKSPACE</div>
        <nav aria-label="Primary navigation">
          {navItems.map(({ label, icon: Icon, count }) => <button key={label} className={`nav-item ${activeNav === label ? 'active' : ''}`} onClick={() => setActiveNav(label)} title={!sidebarOpen ? label : undefined}>
            <Icon size={17} aria-hidden="true" />{sidebarOpen && <><span>{label}</span>{count && <b>{count}</b>}</>}
          </button>)}
        </nav>
        {sidebarOpen && <>
          <div className="workspace-label lower">SYSTEM</div>
          <nav aria-label="System navigation">
            <button className="nav-item" onClick={() => setActiveNav('Diagnostics')}><Gauge size={17} aria-hidden="true" /><span>Diagnostics</span><span className="health-dot" /></button>
            <button className="nav-item" onClick={() => setActiveNav('Settings')}><Settings2 size={17} aria-hidden="true" /><span>Settings</span></button>
          </nav>
          <div className="sidebar-footer"><div className="provider-icon"><ShieldCheck size={16} /></div><div><strong>Provider offline</strong><span>Deterministic QC available</span></div></div>
        </>}
        <button className="sidebar-toggle" aria-label={sidebarOpen ? 'Collapse sidebar' : 'Expand sidebar'} onClick={() => setSidebarOpen(!sidebarOpen)}><PanelLeft size={17} /></button>
      </aside>

      <main className="main-content">
        <header className="topbar">
          <div className="breadcrumbs"><span>Workspace</span><span>/</span><strong>{activeNav}</strong></div>
          <div className="top-actions"><button className="icon-button" aria-label="Help"><CircleHelp size={18} /></button><span className="operator"><span className="avatar">OP</span><span>Operator</span><ChevronDown size={14} /></span></div>
        </header>

        <div className="page-content">
          <section className="page-heading">
            <div><div className="eyebrow">BATCH 24 · 12 ASSETS</div><h1>Review queue</h1><p>Inspect findings and make the next safe decision for each image.</p></div>
            <button className="primary-button"><Upload size={16} /> Add images <span className="button-shortcut">⌘U</span></button>
          </section>

          <section className="stats-grid" aria-label="Queue summary">
            <div className="stat-card"><div className="stat-icon amber"><AlertTriangle size={17} /></div><div><span>Needs review</span><strong>12</strong></div><small>+3 today</small></div>
            <div className="stat-card"><div className="stat-icon green"><CheckCircle2 size={17} /></div><div><span>Ready to upload</span><strong>8</strong></div><small>Verified</small></div>
            <div className="stat-card"><div className="stat-icon blue"><Clock3 size={17} /></div><div><span>Processing</span><strong>4</strong></div><small>1 active job</small></div>
            <div className="stat-card"><div className="stat-icon slate"><CloudOff size={17} /></div><div><span>Provider status</span><strong className="status-text">Offline</strong></div><small>Manual review on</small></div>
          </section>

          <section className="queue-panel">
            <div className="queue-toolbar"><div className="filter-tabs" role="tablist" aria-label="Filter queue">{(['All', 'Review needed', 'Ready', 'Processing', 'Blocked'] as const).map((item) => <button key={item} className={filter === item ? 'selected' : ''} onClick={() => setFilter(item)} role="tab" aria-selected={filter === item}>{item}<span>{item === 'All' ? 24 : item === 'Review needed' ? 12 : item === 'Ready' ? 8 : item === 'Processing' ? 4 : 2}</span></button>)}</div><div className="queue-tools"><label className="search-box"><Search size={15} /><span className="sr-only">Search assets</span><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search assets" /></label><button className="secondary-button"><Filter size={15} /> Filters</button><button className="icon-button bordered" aria-label="More queue options"><MoreHorizontal size={17} /></button></div></div>
            <div className="queue-meta"><span><strong>{filteredAssets.length}</strong> visible assets</span><button className="sort-button">Priority <ChevronDown size={14} /></button></div>
            <div className="asset-list" role="list">
              {filteredAssets.map((asset) => <button key={asset.id} className={`asset-row ${selected.id === asset.id ? 'selected' : ''}`} onClick={() => { setSelectedId(asset.id); setReviewed(false) }} role="listitem">
                <div className="asset-thumb" style={{ background: asset.image }}><ImageIcon size={20} /></div><div className="asset-info"><strong>{asset.name}</strong><span>{asset.id} · {asset.type}</span></div><div className="asset-status"><StatusBadge status={asset.status} /><span>{asset.issue}</span></div><div className="asset-risk"><Risk level={asset.risk} /><span>{asset.time}</span></div><ArrowUpRight className="row-arrow" size={17} aria-hidden="true" />
              </button>)}
              {filteredAssets.length === 0 && <div className="empty-state"><Search size={22} /><strong>No assets match this view</strong><span>Try another filter or search term.</span></div>}
            </div>
            <div className="pagination"><span>Showing {filteredAssets.length} of 24 assets</span><div><button className="page-button" disabled>Previous</button><button className="page-button active">1</button><button className="page-button">2</button><button className="page-button">Next</button></div></div>
          </section>
        </div>
      </main>

      <aside className="inspection-panel" aria-label="Selected asset inspection">
        <div className="inspection-header"><div><span className="eyebrow">SELECTED ASSET</span><h2>Inspection</h2></div><button className="icon-button" aria-label="Close inspection"><XCircle size={18} /></button></div>
        <div className="preview" style={{ background: selected.image }}><div className="preview-toolbar"><button aria-label="Fit image"><Grid2X2 size={15} /></button><span>FIT</span><button aria-label="Open full image"><ArrowUpRight size={15} /></button></div><div className="preview-label"><ImageIcon size={16} /> {selected.name}</div></div>
        <div className="inspection-body"><div className="inspection-title"><div><h3>{selected.name}</h3><span>{selected.id} · Normalized JPEG</span></div><StatusBadge status={selected.status} /></div>
          <div className="next-action"><div className="action-label"><span className="pulse-dot" /> NEXT SAFE ACTION</div><strong>{selected.status === 'Ready' ? 'Package is verified' : selected.status === 'Blocked' ? 'Inspect the blocking finding' : selected.status === 'Processing' ? 'Wait for semantic audit' : 'Review the flagged evidence'}</strong><span>{selected.issue}</span></div>
          <section className="evidence-section"><div className="section-heading"><h4>Evidence summary</h4><span>3 checks</span></div><div className="evidence-item"><CheckCircle2 size={16} className="evidence-good" /><div><strong>Technical QC</strong><span>Resolution, JPEG, color and sharpness</span></div><b>PASS</b></div><div className="evidence-item"><AlertTriangle size={16} className="evidence-warn" /><div><strong>Semantic audit</strong><span>{selected.issue}</span></div><b className="attention">REVIEW</b></div><div className="evidence-item"><CheckCircle2 size={16} className="evidence-good" /><div><strong>Metadata</strong><span>35 keywords · 1 title proposal</span></div><b>PASS</b></div></section>
          <section className="provenance"><div className="section-heading"><h4>Provenance</h4><button aria-label="Refresh provenance"><RefreshCw size={14} /></button></div><dl><div><dt>Policy version</dt><dd>wave1-baseline-2026-09</dd></div><div><dt>Artifact hash</dt><dd>8f2a…c19e</dd></div><div><dt>Last audited</dt><dd>Today, 10:42 AM</dd></div></dl></section>
        </div>
        <div className="inspection-actions"><button className="secondary-button" onClick={() => setReviewed(!reviewed)}><ShieldCheck size={15} /> {reviewed ? 'Marked reviewed' : 'Mark reviewed'}</button><button className="primary-button" disabled={selected.status === 'Blocked'}><Check size={16} /> Approve</button></div>
      </aside>
    </div>
  )
}

export { App }
